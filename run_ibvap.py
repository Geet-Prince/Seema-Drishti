"""
run_ibvap.py â€” IBVAP Single Entry Point (V8 Multi-Camera Architecture)
=============================================================================
Changes from V7:
1. Multi-Camera AI: ALL cameras get YOLO detection, not just one.
2. Per-Camera IOU Tracking: Simple IOU tracker per camera (no ByteTrack
   cross-camera contamination).
3. Per-Camera Virtual Fence: Each camera loads its own fence polygon.
4. ANPR Integration: Automatic plate reading on detected vehicles.
5. Better error handling for bad/black video files.
"""
# ── macOS OpenMP fix ─────────────────────────────────────────────────────────
# PyTorch and insightface each bundle their own libomp.dylib. On macOS loading
# both in the same process triggers "OMP Error #15" and aborts the program.
# Setting this env-var BEFORE any import suppresses the abort safely.
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
# ─────────────────────────────────────────────────────────────────────────────
import sys
import queue
import threading
import time
import cv2
import subprocess

# Auto-install missing packages for the user's specific environment
try:
    import multipart
except ImportError:
    print("Auto-installing python-multipart into your environment...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-multipart"])
    
try:
    import insightface
except ImportError:
    print("Auto-installing insightface and faiss-cpu into your environment...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "insightface", "faiss-cpu", "onnxruntime"])

import uvicorn
import numpy as np
import torch
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ultralytics import YOLO
from suspicious_activity.loitering_detector import SuspiciousActivityDetector
from virtual_fence.fence_detector import VirtualFence
from alarm_manager.src.core import AlarmManager
from alarm_manager.src.frame_buffer import CAMERA_REGISTRY
from contracts.schema import DetectionResult, DetectedObject

# Try to import ANPR (optional â€” needs easyocr)
try:
    from anpr.plate_reader import PlateReader
    _ANPR_AVAILABLE = True
except Exception:
    _ANPR_AVAILABLE = False


# â”€â”€ Simple IOU Tracker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class KalmanTracker:
    """Per-camera tracker with Kalman filter + HSV appearance embeddings.

    1. Constant-velocity Kalman filter per track: smooth bbox interpolation
       between YOLO frames so render runs at 30 FPS even when YOLO is at 8.
    2. HSV histogram appearance (512-d, no extra model, <0.5 ms/det):
       combined IoU + cosine cost prevents ID swaps when people cross paths.
    """

    def __init__(self, iou_thresh: float = 0.25, max_lost: int = 20):
        import threading
        self._lock = threading.Lock()
        self.tracks: dict = {}   # tid -> {kf, emb, lost, bbox, cls, conf}
        self.next_id: int = 1
        self.iou_thresh = iou_thresh
        self.max_lost = max_lost

    @staticmethod
    def _make_kf():
        """State=[cx,cy,w,h,vx,vy], observation=[cx,cy,w,h]."""
        kf = cv2.KalmanFilter(6, 4)
        kf.transitionMatrix = np.float32([
            [1,0,0,0,1,0],
            [0,1,0,0,0,1],
            [0,0,1,0,0,0],
            [0,0,0,1,0,0],
            [0,0,0,0,1,0],
            [0,0,0,0,0,1],
        ])
        kf.measurementMatrix = np.float32([
            [1,0,0,0,0,0],
            [0,1,0,0,0,0],
            [0,0,1,0,0,0],
            [0,0,0,1,0,0],
        ])
        kf.processNoiseCov     = np.eye(6, dtype=np.float32) * 1e-2
        kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * 1e-1
        kf.errorCovPost        = np.eye(6, dtype=np.float32)
        return kf

    @staticmethod
    def _xyxy_to_z(bbox):
        x1, y1, x2, y2 = bbox
        return np.float32([(x1+x2)/2, (y1+y2)/2, x2-x1, y2-y1]).reshape(4, 1)

    @staticmethod
    def _z_to_xyxy(state):
        st = state.flatten(); cx, cy, w, h = float(st[0]), float(st[1]), float(st[2]), float(st[3])
        return (int(cx-w/2), int(cy-h/2), int(cx+w/2), int(cy+h/2))

    @staticmethod
    def _hsv_emb(frame, bbox):
        """Fast 512-d HSV histogram embedding, L2-normalised."""
        x1, y1, x2, y2 = (max(0, int(v)) for v in bbox)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        crop = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA)
        hsv  = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0,1,2], None, [8,8,8],
                            [0,180, 0,256, 0,256]).flatten().astype(np.float32)
        n = np.linalg.norm(hist)
        return hist / n if n > 0 else hist

    @staticmethod
    def _iou_matrix(t_bboxes, d_bboxes):
        if not t_bboxes or not d_bboxes:
            return np.zeros((len(t_bboxes), len(d_bboxes)), dtype=np.float32)
        t = np.asarray(t_bboxes, dtype=np.float32)
        d = np.asarray(d_bboxes, dtype=np.float32)
        x1 = np.maximum(t[:,0:1], d[None,:,0])
        y1 = np.maximum(t[:,1:2], d[None,:,1])
        x2 = np.minimum(t[:,2:3], d[None,:,2])
        y2 = np.minimum(t[:,3:4], d[None,:,3])
        inter = np.maximum(0, x2-x1) * np.maximum(0, y2-y1)
        at = ((t[:,2]-t[:,0])*(t[:,3]-t[:,1]))[:,None]
        ad = ((d[:,2]-d[:,0])*(d[:,3]-d[:,1]))[None,:]
        union = at + ad - inter
        return np.where(union>0, inter/union, 0.0).astype(np.float32)

    def predict(self) -> dict:
        with self._lock:
            """Advance Kalman filters one step. Returns {tid: xyxy_bbox}.
            Call every render frame -- keeps boxes moving smoothly when YOLO
            is skipped. Cost: pure NumPy matrix ops, negligible on CPU."""
            predicted = {}
            for tid, t in self.tracks.items():
                state = t['kf'].predict()
                predicted[tid] = self._z_to_xyxy(state)
            return predicted

    def update(self, detections: list, frame=None) -> list:
        with self._lock:
            """Match detections to tracks (IoU+appearance), correct Kalman."""
            for v in self.tracks.values():
                v['lost'] += 1

            matched: dict = {}
            unmatched = list(range(len(detections)))

            if self.tracks and detections:
                tids   = list(self.tracks.keys())
                t_bboxes = [self._z_to_xyxy(self.tracks[tid]['kf'].statePost.flatten()) for tid in tids]
                d_bboxes = [det['bbox'] for det in detections]

                iou_mat = self._iou_matrix(t_bboxes, d_bboxes)
                app_mat = np.zeros_like(iou_mat)
                if frame is not None:
                    for ti, tid in enumerate(tids):
                        t_emb = self.tracks[tid].get('emb')
                        if t_emb is None:
                            continue
                        for di, det in enumerate(detections):
                            d_emb = self._hsv_emb(frame, det['bbox'])
                            if d_emb is not None:
                                app_mat[ti, di] = float(np.dot(t_emb, d_emb))

                cost_mat = 0.5 * iou_mat + 0.5 * app_mat
                remaining = list(range(len(detections)))
                for t_i in np.argsort(-cost_mat.max(axis=1)):
                    if not remaining:
                        break
                    tid = tids[t_i]
                    best_di = max(remaining, key=lambda di: cost_mat[t_i, di])
                    if float(cost_mat[t_i, best_di]) >= self.iou_thresh:
                        matched[best_di] = tid
                        remaining.remove(best_di)
                        z = self._xyxy_to_z(detections[best_di]['bbox'])
                        self.tracks[tid]['kf'].correct(z)
                        self.tracks[tid]['lost'] = 0
                        self.tracks[tid]['bbox'] = detections[best_di]['bbox']
                        if frame is not None:
                            new_emb = self._hsv_emb(frame, detections[best_di]['bbox'])
                            if new_emb is not None:
                                old = self.tracks[tid].get('emb')
                                if old is None:
                                    self.tracks[tid]['emb'] = new_emb
                                else:
                                    merged = 0.7*old + 0.3*new_emb
                                    n = np.linalg.norm(merged)
                                    self.tracks[tid]['emb'] = merged/n if n > 0 else merged
                unmatched = remaining

            for di in unmatched:
                tid = self.next_id; self.next_id += 1
                kf = self._make_kf()
                z  = self._xyxy_to_z(detections[di]['bbox'])
                kf.statePost[:4] = z
                kf.statePost[4:] = 0.0
                emb = self._hsv_emb(frame, detections[di]['bbox']) if frame is not None else None
                self.tracks[tid] = {
                    'kf': kf, 'emb': emb, 'lost': 0,
                    'bbox': detections[di]['bbox'],
                    'cls':  detections[di].get('cls', 0),
                    'conf': detections[di].get('conf', 1.0),
                }
                matched[di] = tid

            dead = [t for t, v in self.tracks.items() if v['lost'] > self.max_lost]
            for t in dead:
                del self.tracks[t]

            for i, det in enumerate(detections):
                det['track_id'] = matched.get(i, 0)
            return detections


# â”€â”€ Threaded Video Capture â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# -- Smart Motion Gating -------------------------------------------------------
class MotionDetector:
    def __init__(self):
        # MOG2 is extremely fast and robust to lighting changes
        self.fgbg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=30, detectShadows=False)
        self.cooldown = 0
        self.skip_frames = 0
        
    def has_motion(self, frame) -> bool:
        self.skip_frames = (self.skip_frames + 1) % 3
        if self.skip_frames != 0:
            if self.cooldown > 0:
                self.cooldown -= 1
                return True
            return False

        small = cv2.resize(frame, (320, 180))
        fgmask = self.fgbg.apply(small)
        score = cv2.countNonZero(fgmask)
        
        # 500 pixels of motion in a 320x180 frame is a solid moving object
        if score > 300:
            self.cooldown = 45  # Keep AI awake for 45 frames after motion stops (~1.5s)
        else:
            if self.cooldown > 0:
                self.cooldown -= 1
                
        return self.cooldown > 0

class ThreadedCamera:

    def __init__(self, src_str: str, cam_id: str, name: str,
                 w: int, h: int, start_active: bool = True):
        self.src_str = src_str
        self.id = cam_id
        self.name = name
        self.w = w
        self.h = h
        self.is_active = start_active
        self.cap = None

        self.suspicious = SuspiciousActivityDetector()
        self.fence = VirtualFence(cam_id=cam_id, video_name=name,
                                  frame_w=w, frame_h=h)
        self.tracker = KalmanTracker()

        self.latest_frame = np.zeros((h, w, 3), dtype=np.uint8)
        self.latest_frame_id = 0
        self.last_analyzed = None
        self.last_raw_vehicles: list = []
        self.running = True
        self.track_history: dict = {}
        self.vehicle_plates: dict = {}          # track_key -> plate string
        self.vehicle_plate_retries: dict = {}   # track_key -> retry count
        self.vehicle_best_conf: dict = {}       # track_key -> float
        self._decode_failures = 0
        self.video_ended = False

        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    # â”€â”€ Background reader â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _update(self):
        fps = 25.0
        frame_time = 1.0 / fps

        while self.running:
            if not self.is_active:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                self.video_ended = False
                time.sleep(0.5)
                continue

            if getattr(self, 'video_ended', False):
                time.sleep(0.1)
                continue

            if self.cap is None:
                self.cap = cv2.VideoCapture(self.src_str)
                if self.cap.isOpened():
                    fps = self.cap.get(cv2.CAP_PROP_FPS)
                    if fps <= 0 or fps > 60:
                        fps = 25.0
                    frame_time = 1.0 / fps
                else:
                    print(f"  [WARN] {self.id}: Failed to open {self.src_str}")
                    self._decode_failures += 1
                    time.sleep(2.0)
                    continue

            loop_start = time.time()
            ret, frame = self.cap.read() if self.cap else (False, None)

            if not ret:
                if self.cap and self.cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0:
                    # It's a video file and we reached the end. 
                    # Pause playback until user switches camera away and back.
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    # Reset tracker to avoid teleportation artifacts
                    self.tracker = KalmanTracker()
                else:
                    self._decode_failures += 1
                    if self._decode_failures > 100:
                        print(f"  [WARN] {self.id}: Too many decode failures, "
                              f"re-opening sourceâ€¦")
                        if self.cap:
                            self.cap.release()
                            self.cap = None
                        self._decode_failures = 0
                        time.sleep(1.0)
                continue

            # Good frame â€” reset failure counter.
            self._decode_failures = 0
            self.latest_frame = frame
            self.latest_frame_id += 1

            elapsed = time.time() - loop_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def release(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()


# â”€â”€ Consolidated Batched AI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class ConsolidatedBatchedAI:
    """Runs a single YOLOv8 model on a batch of ALL camera frames using
    ``predict()`` for pure detection (no tracking state to contaminate)."""

    def __init__(self):
        # ── Device detection: CUDA → MPS → CPU. Never hardcode device=0. ──
        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            self._device = 0
            self._use_half = True
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            import os as _os
            # PyTorch MPS suffers from GC threading crashes on YOLO batching. 
            # Default to CPU which is incredibly fast and 100% stable on Apple Silicon.
            self._device = _os.environ.get("IBVAP_DEVICE", "cpu")
            self._use_half = False
        else:
            self._device = "cpu"
            self._use_half = False
        print(f"  [AI] Device: {self._device} | FP16: {self._use_half}")

        import os
        from pathlib import Path
        _default_engine = Path(__file__).resolve().parent / 'yolov8s.engine'
        _ENGINE = Path(os.environ.get('IBVAP_TRT_ENGINE', str(_default_engine)))
        _FALLBACK = os.environ.get('IBVAP_YOLO_WEIGHTS', 'yolov8s.pt')

        # TensorRT .engine only runs on NVIDIA CUDA — never load it on Mac/CPU.
        if _ENGINE.exists() and torch.cuda.is_available() and torch.cuda.device_count() > 0:
            self.model = YOLO(str(_ENGINE))
            self._using_trt = True
            print('  [AI] TensorRT engine loaded — FP16, fused kernels active')
        else:
            if _ENGINE.exists():
                print('  [AI] Engine file present but no CUDA — skipping TRT, using PyTorch weights')
            print(f'  [AI] Loading {_FALLBACK} on {self._device} ...')
            self.model = YOLO(_FALLBACK)
            try:
                self.model.to(self._device)
            except Exception as _e:
                print(f'  [WARN] model.to({self._device}) failed ({_e}); falling back to cpu')
                self._device = "cpu"
                self.model.to("cpu")
            self._using_trt = False
            if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                try:
                    self.model.model = torch.compile(
                        self.model.model, mode='reduce-overhead', fullgraph=False
                    )
                    print('  [AI] torch.compile enabled')
                except Exception as _e:
                    print(f'  [WARN] torch.compile unavailable: {_e}')

        self._anpr = None
        if _ANPR_AVAILABLE:
            try:
                self._anpr = PlateReader()
                print('  [ANPR] Plate reader initialised.')
                import queue, threading
                self._anpr_queue = queue.Queue(maxsize=50)
                self._anpr_results = {}
                self._anpr_lock = threading.Lock()
                self._anpr_thread = threading.Thread(target=self._anpr_worker_loop, daemon=True)
                self._anpr_thread.start()
            except Exception as exc:
                print(f'  [WARN] ANPR init failed: {exc}')

    def _anpr_worker_loop(self):
        import hashlib, cv2
        from pathlib import Path
        while True:
            try:
                cam_id, track_key, frame_crop = self._anpr_queue.get()
                if self._anpr is not None:
                    plate = self._anpr.read_plate(frame_crop)
                    if plate:
                        with self._anpr_lock:
                            self._anpr_results[(cam_id, track_key)] = plate
                        
                        try:
                            incident_id = hashlib.md5(f"{cam_id}-{track_key}".encode()).hexdigest()[:12]
                            inc_dir = Path(__file__).resolve().parent / "storage" / "incidents" / cam_id / incident_id
                            inc_dir.mkdir(parents=True, exist_ok=True)
                            cv2.imwrite(str(inc_dir / f"plate_{plate}.jpg"), frame_crop)
                            
                            # Also save to a global plates folder
                            plates_dir = Path(__file__).resolve().parent / "storage" / "plates" / cam_id
                            plates_dir.mkdir(parents=True, exist_ok=True)
                            cv2.imwrite(str(plates_dir / f"plate_{plate}.jpg"), frame_crop)
                        except Exception as e:
                            print("Plate save error:", e)

                self._anpr_queue.task_done()
            except Exception as e:
                print("ALARM WORKER ERROR:", e)

    def warmup(self, n_cams: int = 1) -> None:
        try:
            dev = getattr(self, "_device", "cpu")
            if getattr(self, '_using_trt', False):
                # Init the predictor with a single frame
                self.model.predict([np.zeros((640, 640, 3), dtype=np.uint8)], device=dev, verbose=False, workers=0)
                backend = getattr(self.model.predictor, 'model', None)
                if backend and hasattr(backend, 'bindings'):
                    shape = backend.bindings['images'].shape
                    self.max_batch = int(shape[0]) if shape[0] > 0 else 1
                    self.is_dynamic_batch = getattr(backend, 'dynamic', False)
                else:
                    self.max_batch = 1
                    self.is_dynamic_batch = False
                print(f'  [AI] TRT Model max batch size: {self.max_batch} (dynamic: {self.is_dynamic_batch})')
                if self.max_batch > 1:
                    dummy = [np.zeros((640, 640, 3), dtype=np.uint8)] * min(n_cams, self.max_batch)
                    self.model.predict(dummy, device=dev, verbose=False, workers=0)
            else:
                for bs in sorted({1, min(n_cams, 4)}):
                    dummy = [np.zeros((640, 640, 3), dtype=np.uint8)] * bs
                    self.model.predict(dummy, device=dev, verbose=False, workers=0)
                self.max_batch = 16
                self.is_dynamic_batch = True
            print(f'  [AI] Warmup done on {dev}')
        except Exception as exc:
            print(f'Warmup error: {exc}')

    # ------------------------------------------------------------------ #
    def process_batch(
        self,
        frames: list[np.ndarray],
        cam_nodes: list,
        ts: datetime,
    ) -> dict:
        """Run YOLO on every camera frame, then per-camera IOU tracking.

        Returns ``{cam_id: (humans_DR, vehicles_DR)}`` where each value
        is a pair of ``DetectionResult`` objects.
        """
        CLASS_MAP = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
        results_map: dict = {}
        if not frames:
            return results_map

        try:
            with torch.no_grad():
                # Batch chunking to avoid TRT max batch size limits
                # TRT engines have a baked-in max batch size. Extract it if possible.
                MAX_BATCH = getattr(self, 'max_batch', 1)
                if MAX_BATCH is None or MAX_BATCH < 1:
                    MAX_BATCH = 1
                yolo_results = []
                _dev = getattr(self, "_device", "cpu")
                _half = getattr(self, "_use_half", False)
                for b_idx in range(0, len(frames), MAX_BATCH):
                    chunk = frames[b_idx:b_idx+MAX_BATCH]
                    _kwargs = dict(
                        source=chunk,
                        classes=[0, 2, 3, 5, 7],
                        conf=0.25,
                        imgsz=416,
                        device=_dev,
                        verbose=False,
                        workers=0,
                    )
                    # 'half' is CUDA-only — only pass it on CUDA to avoid errors on CPU/MPS.
                    # 'half' is deprecated and spammy on MPS. Only use on real CUDA.
                    if _dev == 0 or _dev == "cuda":
                        _kwargs["half"] = True
                    chunk_results = self.model.predict(**_kwargs)
                    yolo_results.extend(chunk_results)

            for i, res in enumerate(yolo_results):
                cam = cam_nodes[i]

                # â”€â”€ Parse raw detections â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # Batch GPU->CPU tensor transfer (3 transfers vs 3N per detection)
                raw_dets = []
                if res.boxes and len(res.boxes):
                    xyxy  = res.boxes.xyxy.cpu().numpy().astype(int)
                    clses = res.boxes.cls.cpu().numpy().astype(int)
                    confs = res.boxes.conf.cpu().numpy()
                    raw_dets = [
                        {"bbox": tuple(map(int, xyxy[j])), "cls": int(clses[j]), "conf": float(confs[j])}
                        for j in range(len(xyxy))
                    ]

                # ── Per-camera IOU tracking ─────────────────────────────
                tracked = cam.tracker.update(raw_dets, frames[i])

                # Cleanup dead tracks from camera memory
                active_tids = set(cam.tracker.tracks.keys())
                for t_key in list(cam.track_history.keys()):
                    tid_str = t_key.split("-det-")[-1] if "-det-" in t_key else ""
                    if tid_str.isdigit() and int(tid_str) not in active_tids:
                        del cam.track_history[t_key]
                for v_key in list(cam.vehicle_plates.keys()):
                    tid_str = v_key.split("-veh-")[-1] if "-veh-" in v_key else ""
                    if tid_str.isdigit() and int(tid_str) not in active_tids:
                        del cam.vehicle_plates[v_key]
                for v_key in list(cam.vehicle_plate_retries.keys()):
                    tid_str = v_key.split("-veh-")[-1] if "-veh-" in v_key else ""
                    if tid_str.isdigit() and int(tid_str) not in active_tids:
                        del cam.vehicle_plate_retries[v_key]
                        del cam.vehicle_plate_retries[v_key]

                # ── Build DetectionResult objects ───────────────────────
                dr_h = DetectionResult(
                    module="human_tracking", camera_id=cam.id,
                    frame_id=cam.latest_frame_id, timestamp_utc=ts,
                    objects=[],
                )
                dr_v = DetectionResult(
                    module="vehicle_detection", camera_id=cam.id,
                    frame_id=cam.latest_frame_id, timestamp_utc=ts,
                    objects=[],
                )

                for det in tracked:
                    x1, y1, x2, y2 = det["bbox"]
                    cls_id = det["cls"]
                    conf = det["conf"]
                    tid = det["track_id"]
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                    if cls_id == 0:
                        # â”€â”€ Human â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        track_key = f"{cam.id}-det-{tid}"
                        attrs: dict = {"centroid": (cx, cy)}

                        if track_key in cam.track_history:
                            pcx, pcy, pt = cam.track_history[track_key]
                            dt = (ts - pt).total_seconds()
                            if dt > 0:
                                attrs["velocity_px_per_s"] = (
                                    (cx - pcx) / dt,
                                    (cy - pcy) / dt,
                                )
                        cam.track_history[track_key] = (cx, cy, ts)

                        dr_h.objects.append(DetectedObject(
                            object_type="human",
                            bbox=(x1, y1, x2, y2),
                            confidence=conf,
                            track_id=track_key,
                            attributes=attrs,
                        ))
                    else:
                        # â”€â”€ Vehicle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        v_attrs: dict = {
                            "vehicle_type": CLASS_MAP.get(cls_id, "vehicle"),
                            "centroid": (cx, cy),
                        }

                        v_track_key = f"veh-{tid}"
                        
                        # Cache plates to avoid running ANPR every frame
                            
                        if v_track_key in cam.vehicle_plates:
                            v_attrs["plate_no"] = cam.vehicle_plates[v_track_key]
                        elif getattr(self, '_anpr', None) is not None:
                            cached = None
                            with getattr(self, '_anpr_lock', None) or __import__('contextlib').nullcontext():
                                if hasattr(self, '_anpr_results'):
                                    cached = self._anpr_results.get((cam.id, v_track_key))
                            if cached:
                                v_attrs["plate_no"] = cached
                                cam.vehicle_plates[v_track_key] = cached
                            elif conf > cam.vehicle_best_conf.get(v_track_key, 0.0) or cam.vehicle_plate_retries.get(v_track_key, 0) < 5:
                                cam.vehicle_best_conf[v_track_key] = max(conf, cam.vehicle_best_conf.get(v_track_key, 0.0))
                                cam.vehicle_plate_retries[v_track_key] = cam.vehicle_plate_retries.get(v_track_key, 0) + 1
                                try:
                                    crop = frames[i][y1:y2, x1:x2].copy()
                                    self._anpr_queue.put_nowait((cam.id, v_track_key, crop))
                                except Exception:
                                    pass

                        dr_v.objects.append(DetectedObject(
                            object_type="vehicle",
                            bbox=(x1, y1, x2, y2),
                            confidence=conf,
                            track_id=f"veh-{tid}",
                            attributes=v_attrs,
                        ))

                results_map[cam.id] = (dr_h, dr_v)

        except Exception as exc:
            print(f"Batch AI error: {exc}")
            import traceback
            traceback.print_exc()

        return results_map


# â”€â”€ Server â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# -- Async YOLO Detector -------------------------------------------------------
class AsyncDetector:
    """Runs YOLO inference in a background daemon thread.

    The main render loop submits the latest frames each cycle (non-blocking)
    and reads results without ever waiting on YOLO. This decouples inference
    speed from render speed: YOLO runs at its natural throughput (8-15 FPS on
    CPU for 10 cameras), while the render loop always hits 30 FPS.

    Architecture:
        submit()  -- called from main thread, stores latest frames, non-blocking
        get_results() -- called from main thread, returns last published results
        _loop()   -- background thread: pulls latest frames, runs YOLO, publishes
    """

    def __init__(self, n_cams: int, target_yolo_fps: int = 10):
        self._ai = None
        self._n_cams = n_cams
        self._min_interval = 1.0 / target_yolo_fps

        self._lock = threading.Lock()
        self._pending_frames: list = []
        self._pending_cams:   list = []
        self._pending_ts = None
        self._has_pending = False

        self._results: dict = {}     # cam_id -> (dr_humans, dr_vehicles)
        self._result_seq: int = 0    # incremented on every new publish

        self._event   = threading.Event()
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"  [ASYNC] YOLO thread started (target {target_yolo_fps} FPS)")

    def submit(self, frames: list, cams: list, ts) -> None:
        """Non-blocking. Always overwrites pending with the very latest frames."""
        with self._lock:
            self._pending_frames = frames
            self._pending_cams   = cams
            self._pending_ts     = ts
            self._has_pending    = True
        self._event.set()

    def get_results(self) -> tuple:
        """Non-blocking. Returns (results_dict, seq_int).
        The seq number lets the main loop detect when new results have arrived."""
        with self._lock:
            return dict(self._results), self._result_seq

    def _loop(self) -> None:
        # Initialize PyTorch MPS context inside this thread!
        self._ai = ConsolidatedBatchedAI()
        self._ai.warmup(n_cams=self._n_cams)
        while self._running:
            if not self._event.wait(timeout=0.05):
                continue
            self._event.clear()

            with self._lock:
                if not self._has_pending:
                    continue
                frames = list(self._pending_frames)
                cams   = list(self._pending_cams)
                ts     = self._pending_ts
                self._has_pending = False

            if not frames:
                continue

            t0 = time.time()
            new_results = self._ai.process_batch(frames, cams, ts)

            with self._lock:
                self._results.update(new_results)
                self._result_seq += 1

            # Throttle to target FPS (avoids hammering CPU when YOLO is fast)
            elapsed = time.time() - t0
            sleep_t = self._min_interval - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    def stop(self) -> None:
        self._running = False
        self._event.set()


def start_server():
    from alarm_manager.src.api import app
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


# â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def main():
    import ctypes
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
        print('  [SYS] Windows 1ms timer precision enabled')
    except Exception:
        pass
    print("=" * 60)
    print("  SEEMA DRISHTI — Border Intelligence Platform (V8 Multi-Camera)")
    print("  Dashboard: http://localhost:8000/ui")
    print("=" * 60)

    srv = threading.Thread(target=start_server, daemon=True)
    srv.start()
    time.sleep(1.5)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=str,
        default=str(
            (Path(__file__).resolve().parent.parent / "clips").resolve()),
    )
    parser.add_argument("--max-cams", type=int, default=16)
    parser.add_argument("--multi-cam-ai", action="store_true", default=True, help="Always run AI on all cameras")
    args = parser.parse_args()

    source_path = Path(args.source)
    video_sources = (
        sorted(source_path.glob("*.mp4"))[:args.max_cams]
        if source_path.is_dir()
        else [args.source]
    )

    cam_nodes: list[ThreadedCamera] = []
    for i, src in enumerate(video_sources):
        src_str = str(src) if isinstance(src, Path) else src
        cap = cv2.VideoCapture(src_str)
        if not cap.isOpened():
            print(f"  [SKIP] Cannot open: {src_str}")
            continue
        ret, test = cap.read()
        cap.release()
        if not ret:
            print(f"  [SKIP] Cannot read frame from: {src_str}")
            continue

        cam_id = f"CAM_{i + 1:02d}"
        name = src.stem if isinstance(src, Path) else str(src)
        CAMERA_REGISTRY.register(cam_id, name=name, source=src_str)

        # ALL cameras start active.
        cam_nodes.append(
            ThreadedCamera(src_str, cam_id, name,
                           test.shape[1], test.shape[0], start_active=True))

    n_cams = len(cam_nodes)
    if not n_cams:
        print("No cameras found. Exiting.")
        return

    print(f"  âœ“ {n_cams} cameras running â€” ALL active, ALL get AI processing")

    alarm_manager = AlarmManager()

    alarm_queue: queue.Queue = queue.Queue(maxsize=200)

    def alarm_worker():
        while True:
            analyzed, frame_copy = alarm_queue.get()
            try:
                alarm_manager.submit(analyzed, frame=frame_copy)
            except Exception as e:
                print("ALARM WORKER ERROR:", e)

    threading.Thread(target=alarm_worker, daemon=True).start()

    try:
        from face_recognition.core import FaceRecognitionWorker, set_pipeline_worker
        face_worker = FaceRecognitionWorker()
        face_worker.start()
        # Register as the global singleton so the API router can hot-reload
        # this exact instance when new personnel are uploaded via the website.
        set_pipeline_worker(face_worker)
        print("  [FACE] Pipeline worker registered as singleton.")
    except Exception as e:
        print(f"Face recognition init failed: {e}")
        face_worker = None

    # Re-enable async background threading (perfectly safe on CPU!)
    async_detector = AsyncDetector(n_cams=len(cam_nodes), target_yolo_fps=2)
    _last_seq = [-1]  # mutable cell — tracks last YOLO publish seq

    # Store cam_nodes reference so the API layer can access fences, etc.
    CAMERA_REGISTRY._cam_nodes = cam_nodes

    max_grid = min(n_cams, 4)
    cols = 2 if max_grid > 1 else 1
    rows = int(np.ceil(max_grid / cols))
    cell_w, cell_h = 480, 270

    global_frame_count = 0
    ALARM_COOLDOWN: dict = {}  # key → last alarm datetime (throttle 1 s per track)

    try:
        while True:
            t_start = time.time()

            ai_cam_id = CAMERA_REGISTRY.active_ai_cam
            if args.multi_cam_ai:
                for cam in cam_nodes: cam.is_active = True
            elif ai_cam_id == '__grid__':
                for i, cam in enumerate(cam_nodes):
                    cam.is_active = (i < max_grid)
            else:
                for cam in cam_nodes:
                    cam.is_active = (cam.id == ai_cam_id)
                    
            # â”€â”€ STAGE 1: DECODE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # ALL cameras decoded each loop for live MJPEG thumbnails
            all_cams: list = []
            all_frames: list = []
            for cam in cam_nodes:
                if cam.latest_frame is not None:
                    all_cams.append(cam)
                    all_frames.append(cam.latest_frame.copy())

            # active_cams = subset that gets AI this cycle
            active_cams: list[ThreadedCamera] = []
            frames: list[np.ndarray] = []
            for cam, fr in zip(all_cams, all_frames):
                if cam.is_active:
                    active_cams.append(cam)
                    frames.append(fr)

            if not all_cams:
                time.sleep(0.01)
                continue

            global_frame_count += 1
            ts = datetime.now(timezone.utc)

            # -- STAGE 2: Submit frames to async YOLO (non-blocking) -----
            # The AsyncDetector runs inference in a background thread at
            # target_yolo_fps (default 10). The render loop never waits.
            t_infer_start = time.time()
            if args.multi_cam_ai:
                ai_frames, ai_cams = [], []
                for f, c in zip(frames, active_cams):
                    if not hasattr(c, 'motion'):
                        c.motion = MotionDetector()
                    # Only run heavy AI if motion is detected (Smart Approach)
                    if c.motion.has_motion(f):
                        ai_frames.append(f)
                        ai_cams.append(c)
            else:
                ai_cam_id = CAMERA_REGISTRY.active_ai_cam
                ai_frames, ai_cams = [], []
                for f, c in zip(frames, active_cams):
                    if c.id == ai_cam_id:
                        ai_frames.append(f); ai_cams.append(c); break
                if not ai_cams and active_cams:
                    ai_frames = [frames[0]]; ai_cams = [active_cams[0]]
            async_detector.submit(ai_frames, ai_cams, ts)

            # Read latest YOLO results (may be from a previous cycle -- OK)
            results_map, cur_seq = async_detector.get_results()
            has_new_yolo = (cur_seq != _last_seq[0])
            if has_new_yolo:
                _last_seq[0] = cur_seq
            t_infer = time.time() - t_infer_start

            # -- Kalman predict step: advance all track filters every frame -
            # This keeps bboxes moving smoothly between YOLO inference frames.
            for cam in active_cams:
                predicted = cam.tracker.predict()
                if cam.last_analyzed and not has_new_yolo:
                    # Update bbox positions using Kalman prediction so the
                    # render shows smooth motion even while YOLO is running.
                    fr_h = frames[active_cams.index(cam)].shape[0] if frames else 9999
                    fr_w = frames[active_cams.index(cam)].shape[1] if frames else 9999
                    for obj in cam.last_analyzed.objects:
                        if obj.object_type == "human":
                            tid_str = obj.track_id.split("-det-")[-1] if "-det-" in obj.track_id else ""
                            if tid_str.isdigit():
                                tid = int(tid_str)
                                if tid in predicted:
                                    px1,py1,px2,py2 = predicted[tid]
                                    obj.bbox = (
                                        max(0, px1), max(0, py1),
                                        min(fr_w, px2), min(fr_h, py2)
                                    )

            # â”€â”€ STAGE 3: TRACKING + SUSPICIOUS + FENCE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            t_track_start = time.time()
            for i, cam in enumerate(active_cams):
                if not args.multi_cam_ai and cam.id != CAMERA_REGISTRY.active_ai_cam:
                    cam.last_analyzed = None
                    continue

                if cam.id in results_map:
                    tracked_humans, tracked_vehicles = results_map[cam.id]
                    cam.last_raw_vehicles = tracked_vehicles.objects

                    # Merge vehicles into the human result for unified
                    # downstream processing (suspicious + fence + alarm).
                    humans_only = [o for o in tracked_humans.objects if o.object_type == "human"]
                    tracked_humans.objects = humans_only + cam.last_raw_vehicles

                    # Face Recognition Interception
                    if face_worker:
                        frame = frames[i]
                        for obj in tracked_humans.objects:
                            if obj.object_type == "human":
                                identity_info = face_worker.get_identity(obj.track_id)
                                if identity_info:
                                    obj.attributes['identity'] = identity_info['name']
                                    obj.attributes['badge_number'] = identity_info.get('badge_number', '')
                                    obj.attributes['image_path'] = identity_info.get('image_path', '')
                                else:
                                    obj.attributes['identity'] = "Unknown"
                                    # Enqueue tighter upper-body crop for clearer face detection
                                    x1, y1, x2, y2 = obj.bbox
                                    h, w = frame.shape[:2]
                                    w_pad = int((x2 - x1) * 0.10)
                                    h_pad = int((y2 - y1) * 0.10)
                                    # Crop top 45% of the body where the head is located
                                    y2_head = min(h, int(y1 + (y2 - y1) * 0.45) + h_pad)
                                    
                                    x1_p, y1_p = max(0, x1 - w_pad), max(0, y1 - h_pad)
                                    x2_p = min(w, x2 + w_pad)
                                    crop = frame[y1_p:y2_head, x1_p:x2_p]
                                    if crop.size > 0:
                                        face_worker.enqueue_crop(obj.track_id, crop)

                    # Suspicious activity heuristics.
                    analyzed = cam.suspicious.process(tracked_humans)
                    # Virtual fence breach checks.
                    analyzed = cam.fence.process(analyzed)
                    cam.last_analyzed = analyzed

                    # Submit to alarm system (non-blocking).
                    for obj in analyzed.objects:
                        is_breach = (obj.attributes.get("zone_state") == "inside")
                        activity = obj.attributes.get("activity")
                        if is_breach or activity:
                            key = f"{cam.id}_{obj.track_id}"
                            if key not in ALARM_COOLDOWN or (ts - ALARM_COOLDOWN[key]).total_seconds() > 1.0:
                                ALARM_COOLDOWN[key] = ts
                                try:
                                    alarm_queue.put_nowait((analyzed, frames[i].copy()))
                                except queue.Full:
                                    pass
                # else: skipped frame — keep cam.last_analyzed for render
            t_track = time.time() - t_track_start

            # ——— STAGE 4: RENDER ———————————————————————————————————————————
            t_render_start = time.time()
            grid = np.zeros(
                (rows * cell_h, cols * cell_w, 3), dtype=np.uint8)

            ai_cam_id = CAMERA_REGISTRY.active_ai_cam
            grid_cams = []
            for cam in active_cams:
                if cam.id == ai_cam_id:
                    grid_cams.append(cam.id)
                    break
            for cam in active_cams:
                if len(grid_cams) >= max_grid:
                    break
                if cam.id not in grid_cams:
                    grid_cams.append(cam.id)

            # Write raw frames to ALL camera MJPEG buffers first (keeps thumbnails live).
            # Then do the full annotated render only for AI-active cameras.
            for cam, raw_fr in zip(all_cams, all_frames):
                if cam not in active_cams:
                    # Non-AI camera: write raw frame + HUD to its MJPEG buffer
                    raw_disp = raw_fr.copy()
                    cam.fence.draw_fence(raw_disp, breach_active=False)
                    cv2.putText(raw_disp, f"{cam.id} [RAW]",
                                (10, 26), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, (150, 150, 150), 2)
                    buf = CAMERA_REGISTRY.get(cam.id)
                    if buf:
                        buf.write(raw_disp)
                    CAMERA_REGISTRY.update_live(cam.id, 0, cam.latest_frame_id)

            for i, cam in enumerate(active_cams):
                display = frames[i]
                analyzed = cam.last_analyzed

                # Draw fence overlay.
                breach_active = False
                if analyzed:
                    breach_active = any(
                        o.attributes.get("zone_state") == "inside"
                        for o in analyzed.objects
                    )
                cam.fence.draw_fence(display, breach_active=breach_active)

                # Draw detection boxes.
                if analyzed:
                    for obj in analyzed.objects:
                        x1, y1, x2, y2 = obj.bbox
                        activity = obj.attributes.get("activity")
                        is_breach = (
                            obj.attributes.get("zone_state") == "inside")
                        identity = obj.attributes.get("identity", "Unknown")
                        badge = obj.attributes.get("badge_number", "")
                        img_path = obj.attributes.get("image_path", "")
                        
                        if identity != "Unknown" and not activity and not is_breach:
                            color = (0, 255, 0)
                        elif is_breach or activity:
                            color = (0, 0, 255) # RED
                        else:
                            color = (255, 0, 0) if obj.object_type == "vehicle" else (0, 255, 0)

                        track_num = obj.track_id.split("-")[-1]
                        
                        if identity != "Unknown":
                            base = f"[{identity} | Badge: {badge}]" if badge else f"[{identity}]"
                        else:
                            base = f"{obj.object_type.capitalize()} {track_num}"

                        # Draw the person's photo next to the bounding box if matched
                        if identity != "Unknown" and img_path:
                            try:
                                import os
                                # Convert absolute web path /storage/... to local path
                                local_path = img_path
                                if local_path.startswith('/storage'):
                                    local_path = str(Path(__file__).resolve().parent / "storage" / img_path.split('/storage/')[-1])
                                if os.path.exists(local_path):
                                    person_img = cv2.imread(local_path)
                                    if person_img is not None:
                                        fh, fw = display.shape[:2]
                                        size = 60 # Thumbnail size
                                        person_img = cv2.resize(person_img, (size, size))
                                        # Top-right corner of the bounding box
                                        py1, py2 = max(0, y1 - size), max(0, y1)
                                        if py2 - py1 < size: # If bounding box is at the very top, draw it inside
                                            py1, py2 = y1, y1 + size
                                        px1, px2 = max(0, x2), max(0, x2) + size
                                        if px2 > fw:
                                            px1, px2 = fw - size, fw
                                        
                                        # Overlay the thumbnail
                                        display[py1:py2, px1:px2] = person_img
                                        # Draw border around thumbnail
                                        cv2.rectangle(display, (px1, py1), (px2, py2), (0, 255, 0), 2)
                            except Exception as e:
                                pass # Ignore drawing errors so pipeline doesn't crash

                        tags: list[str] = []
                        if "vehicle_type" in obj.attributes:
                            tags.append(
                                obj.attributes["vehicle_type"].upper())
                        if "plate_no" in obj.attributes:
                            tags.append(
                                f"[{obj.attributes['plate_no']}]")
                        if activity:
                            tags.append(activity.upper())
                        if is_breach:
                            tags.append("BREACH")
                        if identity == "Unknown" and obj.object_type == "human":
                            tags.append("UNKNOWN")

                        label = (f"{base} {' '.join(tags)}"
                                 if tags else base)
                        cv2.rectangle(
                            display, (int(x1), int(y1)),
                            (int(x2), int(y2)), color, 2)
                        cv2.putText(
                            display, label,
                            (int(x1), int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        if "centroid" in obj.attributes:
                            cx, cy = obj.attributes["centroid"]
                            cv2.circle(
                                display, (int(cx), int(cy)),
                                5, (0, 0, 255), -1)

                obj_count = (len(analyzed.objects)
                             if analyzed else 0)

                # HUD label.
                is_ai = args.multi_cam_ai or cam.id == CAMERA_REGISTRY.active_ai_cam
                status_label = "[AI]" if is_ai else "[RAW]"
                cv2.putText(
                    display,
                    f"{cam.id} {status_label} | Obj: {obj_count}",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 255, 0) if is_ai else (150, 150, 150), 2)

                # Write to per-camera MJPEG buffer.
                buf = CAMERA_REGISTRY.get(cam.id)
                if buf:
                    buf.write(display)
                CAMERA_REGISTRY.update_live(
                    cam.id, obj_count, cam.latest_frame_id)

                # Grid cell.
                if cam.id in grid_cams:
                    g_idx = grid_cams.index(cam.id)
                    r, c = divmod(g_idx, cols)
                    if r < rows:
                        
                        if hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0:
                            gpu_frame = cv2.cuda_GpuMat()
                            gpu_frame.upload(display)
                            cell = cv2.cuda.resize(gpu_frame, (cell_w, cell_h)).download()
                        else:
                            cell = cv2.resize(display, (cell_w, cell_h))
                        grid[r * cell_h:(r + 1) * cell_h,
                             c * cell_w:(c + 1) * cell_w] = cell

            CAMERA_REGISTRY.grid.write(grid)
            t_render = time.time() - t_render_start

            # â”€â”€ FPS Control & Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Cap main loop to ~60 FPS for ultra-smooth M5 rendering
            loop_time = time.time() - t_start
            if loop_time < 1.0 / 60.0:
                time.sleep((1.0 / 60.0) - loop_time)
            elapsed = time.time() - t_start
            fps = 1.0 / elapsed if elapsed > 0 else 0

            if global_frame_count % 30 == 0:
                print(
                    f"[FPS: {fps:.1f}] Cams: {len(active_cams)} | "
                    f"Infer: {t_infer * 1000:.1f}ms | "
                    f"Track: {t_track * 1000:.1f}ms | "
                    f"Render: {t_render * 1000:.1f}ms")

            # Note: torch.cuda.empty_cache() removed from hot loop (causes CUDA stall)

            target_delay = 1.0 / 30.0
            if elapsed < target_delay:
                time.sleep(target_delay - elapsed)

    except KeyboardInterrupt:
        pass
    finally:
        for cam in cam_nodes:
            cam.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        print("Pipeline stopped.")


if __name__ == "__main__":
    main()
