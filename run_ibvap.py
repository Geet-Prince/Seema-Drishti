"""
run_ibvap.py â€” IBVAP Single Entry Point (V8 Multi-Camera Architecture)
=============================================================================
Changes from V7:
1. Multi-Camera AI: ALL cameras get YOLO detect
ion, not just one.
2. Per-Camera IOU Tracking: Simple IOU tracker per camera (no ByteTrack
   cross-camera contamination).
3. Per-Camera Virtual Fence: Each camera loads its own fence polygon.
4. ANPR Integration: Automatic plate reading on detected vehicles.
5. Better error handling for bad/black video files.
"""
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
# ── Render-path caches (hot-loop optimizations, zero inference impact) ──
# Person thumbnails were re-read from disk + decoded + resized EVERY frame for
# every recognized identity. Cache the 60px overlay once per image path.
_THUMB_CACHE: dict = {}
_THUMB_SIZE = 60


def _get_person_thumb(local_path: str):
    """Return a cached 60x60 BGR thumbnail, loading from disk only once."""
    thumb = _THUMB_CACHE.get(local_path)
    if thumb is None:
        import cv2 as _cv2
        import os as _os
        if not local_path or not _os.path.exists(local_path):
            return None
        img = _cv2.imread(local_path)
        if img is None:
            return None
        thumb = _cv2.resize(img, (_THUMB_SIZE, _THUMB_SIZE))
        # Bound memory: thumbnails are ~10KB each; 200 entries is plenty.
        if len(_THUMB_CACHE) >= 200:
            _THUMB_CACHE.clear()
        _THUMB_CACHE[local_path] = thumb
    return thumb


def _resolve_face_path(img_path: str):
    """Resolve a /storage/... web path to a local file, cached per path."""
    key = f"path:{img_path}"
    if key in _THUMB_CACHE:
        return _THUMB_CACHE[key]
    local_path = img_path
    if local_path and local_path.startswith('/storage'):
        try:
            from face_recognition.core import resolve_known_face_path
            local_path = resolve_known_face_path(img_path) or img_path
        except Exception:
            import os
            rel = img_path.split('/storage/')[-1]
            for _base in (Path(__file__).resolve().parent,
                          Path(__file__).resolve().parent.parent):
                _cand = str(_base / "storage" / rel)
                if os.path.exists(_cand):
                    local_path = _cand
                    break
    _THUMB_CACHE[key] = local_path
    return local_path


# OpenCV-CUDA probe hoisted out of the per-cell hot loop: previously
# cv2.cuda.getCudaEnabledDeviceCount() ran for every grid cell every frame.
try:
    import cv2 as _cv2_probe
    _CV2_CUDA = hasattr(_cv2_probe, 'cuda') and _cv2_probe.cuda.getCudaEnabledDeviceCount() > 0
except Exception:
    _CV2_CUDA = False


class SimpleIOUTracker:
    """Per-camera IOU-based tracker for assigning stable track IDs.

    Replaces ByteTrack when multiple cameras are batched through a single
    YOLO model, avoiding cross-camera track-ID contamination that occurs
    when ``model.track(persist=True)`` receives frames from different sources.
    """

    def __init__(self, iou_thresh: float = 0.25, max_lost: int = 15):
        self.tracks: dict[int, dict] = {}   # tid â†’ {"bbox", "lost"}
        self.next_id: int = 1
        self.iou_thresh = iou_thresh
        self.max_lost = max_lost

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _iou_matrix(t_bboxes, d_bboxes):
        """Vectorized IOU matrix."""
        if len(t_bboxes) == 0 or len(d_bboxes) == 0:
            return np.zeros((len(t_bboxes), len(d_bboxes)), dtype=np.float32)
        t = np.asarray(t_bboxes, dtype=np.float32)
        d = np.asarray(d_bboxes, dtype=np.float32)
        x1 = np.maximum(t[:, 0:1], d[None, :, 0])
        y1 = np.maximum(t[:, 1:2], d[None, :, 1])
        x2 = np.minimum(t[:, 2:3], d[None, :, 2])
        y2 = np.minimum(t[:, 3:4], d[None, :, 3])
        inter = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
        area_t = ((t[:, 2] - t[:, 0]) * (t[:, 3] - t[:, 1]))[:, None]
        area_d = ((d[:, 2] - d[:, 0]) * (d[:, 3] - d[:, 1]))[None, :]
        union = area_t + area_d - inter
        return np.where(union > 0, inter / union, 0.0).astype(np.float32)

    # ------------------------------------------------------------------ #
    def update(self, detections):
        """Assign track_id to each detection dict.
        Vectorized with NumPy; no per-pair Python IOU loops.
        """
        for v in self.tracks.values():
            v["lost"] += 1

        matched = {}
        unmatched = list(range(len(detections)))

        if self.tracks and detections:
            tids = sorted(self.tracks.keys())
            t_bboxes = [self.tracks[tid]["bbox"] for tid in tids]
            d_bboxes = [det["bbox"] for det in detections]
            iou_mat = self._iou_matrix(t_bboxes, d_bboxes)

            remaining = list(range(len(detections)))
            for t_i, tid in enumerate(tids):
                if not remaining:
                    break
                best_di = max(remaining, key=lambda di: iou_mat[t_i, di])
                if float(iou_mat[t_i, best_di]) >= self.iou_thresh:
                    matched[best_di] = tid
                    remaining.remove(best_di)
                    self.tracks[tid]["bbox"] = detections[best_di]["bbox"]
                    self.tracks[tid]["lost"] = 0
            unmatched = remaining

        for di in unmatched:
            tid = self.next_id; self.next_id += 1
            matched[di] = tid
            self.tracks[tid] = {"bbox": detections[di]["bbox"], "lost": 0}

        dead = [t for t, v in self.tracks.items() if v["lost"] > self.max_lost]
        for t in dead:
            del self.tracks[t]

        for i, det in enumerate(detections):
            det["track_id"] = matched.get(i, 0)
        return detections


# â”€â”€ Threaded Video Capture â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        self.tracker = SimpleIOUTracker()

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
        # True when the source is a seekable video file (vs live webcam/RTSP).
        # Video files loop forever; live sources use the decode-retry path.
        self._is_file = False

        while self.running:
            if not self.is_active:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                self.video_ended = False
                time.sleep(0.5)
                continue

            if self.cap is None:
                self.cap = cv2.VideoCapture(self.src_str)
                if self.cap.isOpened():
                    fps = self.cap.get(cv2.CAP_PROP_FPS)
                    if fps <= 0 or fps > 60:
                        fps = 25.0
                    frame_time = 1.0 / fps
                    try:
                        self._is_file = float(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) > 0
                    except Exception:
                        self._is_file = False
                else:
                    print(f"  [WARN] {self.id}: Failed to open {self.src_str}")
                    self._decode_failures += 1
                    time.sleep(2.0)
                    continue

            loop_start = time.time()
            ret, frame = self.cap.read() if self.cap else (False, None)

            if not ret:
                if getattr(self, '_is_file', False):
                    # Video file reached the end — rewind and loop.
                    try:
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self.cap.read()
                    except Exception:
                        ret, frame = False, None
                    if not ret:
                        # Corrupt tail / can't seek — reopen and start over.
                        try:
                            self.cap.release()
                        except Exception:
                            pass
                        self.cap = None
                        self._decode_failures = 0
                        continue
                else:
                    self._decode_failures += 1
                    if self._decode_failures > 100:
                        print(f"  [WARN] {self.id}: Too many decode failures, "
                              f"re-opening source…")
                        if self.cap:
                            self.cap.release()
                            self.cap = None
                        self._decode_failures = 0
                        time.sleep(1.0)
                if not ret:
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


# Helper to get the best acceleration device for the host machine.
# Delegates to configs/compute.py: NVIDIA -> CUDA/TensorRT, macOS -> CPU
# (PyTorch MPS aborts sustained YOLO inference), else MPS/CPU.
# Override with IBVAP_DEVICE=cpu|cuda|mps.
def get_best_device():
    try:
        from configs.compute import detect_compute
        return detect_compute()["device"]
    except Exception:
        pass
    import os
    import platform
    forced = os.environ.get("IBVAP_DEVICE", "").strip().lower()
    if forced in ("cpu", "cuda", "cuda:0", "mps"):
        return "cuda:0" if forced == "cuda" else forced
    if torch.cuda.is_available():
        return "cuda:0"
    if platform.system() == "Darwin":
        return "cpu"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# â”€â”€ Consolidated Batched AI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class ConsolidatedBatchedAI:
    """Runs a single YOLOv8 model on a batch of ALL camera frames using
    ``predict()`` for pure detection (no tracking state to contaminate)."""

    def __init__(self):
        import os
        import platform
        from pathlib import Path

        try:
            from configs.compute import (
                detect_compute, ensure_trt_engine,
                apply_torch_thread_limits,
            )
            _compute = detect_compute()
        except Exception:
            _compute = {"device": get_best_device(), "use_half": False,
                        "use_trt": False, "gpu_name": "",
                        "note": "compute probe unavailable"}
            def ensure_trt_engine(pt, eng=None, imgsz=640):  # type: ignore
                return pt
            def apply_torch_thread_limits():  # type: ignore
                pass
        print(f"  [COMPUTE] {_compute.get('note', '')}")
        if _compute.get("gpu_name") and not _compute.get("use_trt"):
            print(f"  [COMPUTE] GPU present but unused: {_compute['note']}")

        try:
            self.imgsz = int(os.environ.get("IBVAP_IMGSZ", "640"))
        except ValueError:
            self.imgsz = 640
        if self.imgsz not in (320, 416, 480, 640, 800, 960, 1280):
            self.imgsz = 640

        _default_engine = Path(__file__).resolve().parent / 'yolov8s.engine'
        _coreml_model = Path(__file__).resolve().parent / 'yolov8s.mlpackage'
        _ENGINE = Path(os.environ.get('IBVAP_TRT_ENGINE', str(_default_engine)))
        _COREML = Path(os.environ.get('IBVAP_COREML_MODEL', str(_coreml_model)))
        _FALLBACK = str(Path(__file__).resolve().parent / 'yolov8s.pt')

        self._using_trt = False
        self._using_coreml = False
        if platform.system() == "Darwin":
            # Apple Neural Engine path: reuse a .mlpackage built from this
            # exact .pt, else build it once (FP32, same weights — no accuracy
            # change). Falls back to PyTorch CPU, never crashes.
            try:
                from configs.compute import ensure_coreml_model
                weights = ensure_coreml_model(_FALLBACK, str(_COREML),
                                              imgsz=self.imgsz)
            except Exception as exc:
                print(f'  [WARN] CoreML probe failed ({exc}); using {_FALLBACK}')
                weights = _FALLBACK
            if weights != _FALLBACK:
                print(f'  [NPU] CoreML model found ({Path(weights).name}). Loading Apple Neural Engine format...')
            try:
                self.model = YOLO(str(weights))
                self._using_coreml = str(weights).endswith(".mlpackage")
                if self._using_coreml:
                    print('  [NPU] CoreML model loaded — Apple Neural Engine / GPU acceleration active')
            except Exception as exc:
                print(f'  [WARN] Failed to load {weights} ({exc}); falling back to {_FALLBACK}')
                self.model = YOLO(_FALLBACK)
            self.device = "cpu"
        else:
            # TensorRT path (NVIDIA only): reuse a compatible .engine, else
            # try a one-time export from .pt (GPU-specific build), else .pt.
            # A foreign .engine raises on load — always fall back, never crash.
            weights = _FALLBACK
            if _compute.get("use_trt"):
                if not _ENGINE.exists():
                    print('  [GPU] No TensorRT engine found — building one from '
                          f'{Path(_FALLBACK).name} (one-time, ~1-3 min)...')
                weights = ensure_trt_engine(_FALLBACK, str(_ENGINE),
                                            imgsz=self.imgsz)
            elif _ENGINE.exists():
                print(f'  [INFO] TensorRT engine present but unusable here '
                      f'({_compute.get("note", "no CUDA")}). Using '
                      f'{Path(_FALLBACK).name} on {_compute.get("device", "cpu")}.')
            else:
                print(f'  [WARN] Engine not found at {_ENGINE}, falling back to {_FALLBACK}')
            try:
                print(f'  [AI] Loading {Path(weights).name}...')
                self.model = YOLO(str(weights))
                self._using_trt = str(weights).endswith(".engine")
                if self._using_trt:
                    print('  [GPU] TensorRT engine loaded — FP16, fused kernels active')
            except Exception as exc:
                print(f'  [WARN] Failed to load {weights} ({exc}); falling back to {_FALLBACK}')
                self.model = YOLO(_FALLBACK)
                self._using_trt = False
            if self._using_trt:
                self.device = 0
            else:
                self.device = _compute.get("device", get_best_device())
                try:
                    self.model.to(self.device)
                except Exception as exc:
                    print(f'  [WARN] model.to({self.device}) failed ({exc}); using CPU')
                    self.device = "cpu"
                print(f'  [AI] Model loaded on device: {self.device} (imgsz={self.imgsz})')
                if _compute.get("use_trt") or (
                        str(self.device).startswith("cuda") and torch.cuda.is_available()):
                    try:
                        self.model.model = torch.compile(
                            self.model.model, mode='reduce-overhead', fullgraph=False
                        )
                        print('  [GPU] torch.compile enabled (extra kernel fusion)')
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

        # Serialise all torch inference through one lock. PyTorch MPS is not
        # thread-safe; even on CUDA/CPU this avoids surprises when the ANPR
        # worker (easyocr/torch) runs concurrently with YOLO.
        import threading as _th
        self._infer_lock = _th.Lock()
        # Number-plate watchlist (normalized plate -> row). Refreshed from
        # SQLite every ~15s so newly added plates take effect live.
        self._watchlist: set = set()
        self._watchlist_meta: dict = {}
        self._watchlist_checked_at: float = 0.0
        self._refresh_watchlist(force=True)
        # Keep CPU thread usage bounded so background decode/render threads
        # don't starve inference (tune via IBVAP_TORCH_THREADS). Same bounds
        # suit M5 efficiency cores and NVIDIA hosts.
        try:
            apply_torch_thread_limits()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def _refresh_watchlist(self, force: bool = False) -> None:
        """Reload the plate watchlist from SQLite (throttled to ~15s)."""
        import time as _t
        now = _t.time()
        if not force and now - self._watchlist_checked_at < 15.0:
            return
        self._watchlist_checked_at = now
        try:
            from alarm_manager.src.database import get_watchlist_plates
            rows = get_watchlist_plates()
            self._watchlist = {r["plate"] for r in rows}
            self._watchlist_meta = {r["plate"]: r for r in rows}
        except Exception:
            pass

    def _check_watchlist(self, plate: str | None) -> dict | None:
        """Return the watchlist row if a detected plate is wanted, else None."""
        if not plate:
            return None
        self._refresh_watchlist()
        if not self._watchlist:
            return None
        try:
            from alarm_manager.src.database import normalize_plate
            norm = normalize_plate(plate)
        except Exception:
            norm = "".join(c for c in (plate or "").upper() if c.isalnum())
        if norm in self._watchlist:
            return self._watchlist_meta.get(norm, {"plate": norm})
        return None

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
            with self._infer_lock:
                if getattr(self, '_using_trt', False):
                    # Init the predictor with a single frame
                    self.model.predict([np.zeros((640, 640, 3), dtype=np.uint8)], device=self.device, verbose=False)
                    backend = getattr(self.model.predictor, 'model', None)
                    if backend and hasattr(backend, 'bindings'):
                        shape = backend.bindings['images'].shape
                        self.max_batch = int(shape[0]) if shape[0] > 0 else 1
                        self.is_dynamic_batch = getattr(backend, 'dynamic', False)
                    else:
                        self.max_batch = 1
                        self.is_dynamic_batch = False
                    print(f'  [GPU] TRT Model max batch size: {self.max_batch} (dynamic: {self.is_dynamic_batch})')
                    if self.max_batch > 1:
                        dummy = [np.zeros((640, 640, 3), dtype=np.uint8)] * min(n_cams, self.max_batch)
                        self.model.predict(dummy, device=self.device, verbose=False)
                else:
                    for bs in sorted({1, min(n_cams, 4)}):
                        dummy = [np.zeros((640, 640, 3), dtype=np.uint8)] * bs
                        self.model.predict(dummy, device=self.device, verbose=False)
                        # Flush MPS command buffers between warmup steps; on CPU this is a no-op.
                        try:
                            if self.device == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                                torch.mps.synchronize()
                        except Exception:
                            pass
                    self.max_batch = 16
                    self.is_dynamic_batch = True
            print(f'  [GPU] Warmup done (device={self.device})')
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
            with self._infer_lock, torch.no_grad():
                # Batch chunking to avoid TRT max batch size limits
                # TRT engines have a baked-in max batch size. Extract it if possible.
                MAX_BATCH = getattr(self, 'max_batch', 1)
                if MAX_BATCH is None or MAX_BATCH < 1:
                    MAX_BATCH = 1
                yolo_results = []
                for b_idx in range(0, len(frames), MAX_BATCH):
                    chunk = frames[b_idx:b_idx+MAX_BATCH]
                    chunk_results = self.model.predict(
                        source=chunk,
                        classes=[0, 2, 3, 5, 7],
                        conf=0.25,
                        imgsz=getattr(self, 'imgsz', 640),
                        device=self.device,

                        verbose=False,
                    )
                    yolo_results.extend(chunk_results)
                # On MPS, wait for the command buffer to finish before the
                # next predict() / background torch use. Prevents the
                # AGXG17GFamilyCommandBuffer coalescing abort.
                try:
                    if self.device == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                        torch.mps.synchronize()
                except Exception:
                    pass

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
                tracked = cam.tracker.update(raw_dets)

                # Cleanup dead tracks from camera memory
                active_tids = set(cam.tracker.tracks.keys())
                for tid in list(cam.track_history.keys()):
                    if tid not in active_tids:
                        del cam.track_history[tid]
                for v_key in list(cam.vehicle_plates.keys()):
                    tid_str = v_key.replace("veh-", "")
                    if tid_str.isdigit() and int(tid_str) not in active_tids:
                        del cam.vehicle_plates[v_key]
                for v_key in list(cam.vehicle_plate_retries.keys()):
                    tid_str = v_key.replace("veh-", "")
                    if tid_str.isdigit() and int(tid_str) not in active_tids:
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
                        track_key = f"det-{tid}"
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

                        # Number-plate watchlist check — flags wanted vehicles
                        # for the critical "Watchlist Plate Detected" rule and
                        # captures a driver-region crop for evidence.
                        if v_attrs.get("plate_no"):
                            wl_row = self._check_watchlist(v_attrs["plate_no"])
                            if wl_row is not None:
                                v_attrs["watchlist_match"] = True
                                v_attrs["watchlist_owner"] = wl_row.get("owner", "")
                                print(f"  [WATCHLIST] {cam.id} {v_track_key} plate {v_attrs['plate_no']} — wanted vehicle!")
                                try:
                                    import hashlib as _hl
                                    from pathlib import Path as _P
                                    _iid = _hl.md5(f"{cam.id}-{v_track_key}".encode()).hexdigest()[:12]
                                    _idir = _P(__file__).resolve().parent / "storage" / "incidents" / cam.id / _iid
                                    _idir.mkdir(parents=True, exist_ok=True)
                                    if not next(_idir.glob("driver_*.jpg"), None):
                                        import cv2 as _cv2
                                        _fr = frames[i]
                                        _fh, _fw = _fr.shape[:2]
                                        _bw, _bh = x2 - x1, y2 - y1
                                        _dx1 = max(0, x1 - int(_bw * 0.10))
                                        _dx2 = min(_fw, x2 + int(_bw * 0.10))
                                        _dy1 = max(0, y1 - int(_bh * 0.15))
                                        _dy2 = min(_fh, y1 + int(_bh * 0.55))
                                        if _dx2 - _dx1 >= 20 and _dy2 - _dy1 >= 20:
                                            _crop = _fr[_dy1:_dy2, _dx1:_dx2]
                                            if _crop.size > 0:
                                                _cv2.imwrite(str(_idir / "driver_001.jpg"), _crop,
                                                             [_cv2.IMWRITE_JPEG_QUALITY, 90])
                                except Exception as _e:
                                    print(f"  [WARN] driver capture failed: {_e}")

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
    parser.add_argument("--multi-cam-ai", action="store_true", help="Enable AI processing on all cameras simultaneously")
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
        from face_recognition.core import FaceRecognitionWorker
        face_worker = FaceRecognitionWorker()
        face_worker.start()
    except Exception as e:
        print(f"Face recognition init failed: {e}")
        face_worker = None

    batched_ai = ConsolidatedBatchedAI()
    batched_ai.warmup(n_cams=len(cam_nodes))

    # Store cam_nodes reference so the API layer can access fences, etc.
    CAMERA_REGISTRY._cam_nodes = cam_nodes

    max_grid = min(n_cams, 4)
    cols = 2 if max_grid > 1 else 1
    rows = int(np.ceil(max_grid / cols))
    cell_w, cell_h = 480, 270

    global_frame_count = 0
    ALARM_COOLDOWN: dict[str, datetime] = {}

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

            # Run YOLO every 2nd frame for accuracy/perf balance.
            run_yolo = (global_frame_count % 2 == 0)

            # â”€â”€ STAGE 2: BATCHED INFERENCE ON ALL CAMERAS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            t_infer_start = time.time()
            results_map: dict = {}
            if run_yolo:
                if args.multi_cam_ai:
                    ai_frames = frames
                    ai_cams = active_cams
                else:
                    ai_cam_id = CAMERA_REGISTRY.active_ai_cam
                    ai_frames = []
                    ai_cams = []
                    for f, c in zip(frames, active_cams):
                        if c.id == ai_cam_id:
                            ai_frames.append(f)
                            ai_cams.append(c)
                            break
                    if not ai_cams and active_cams:
                        ai_frames = [frames[0]]
                        ai_cams = [active_cams[0]]
                
                results_map = batched_ai.process_batch(ai_frames, ai_cams, ts)
            t_infer = time.time() - t_infer_start

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
                        is_wanted = bool(obj.attributes.get("watchlist_match"))
                        if is_breach or activity or is_wanted:
                            key = f"{cam.id}_{obj.track_id}"
                            if key not in ALARM_COOLDOWN or (ts - ALARM_COOLDOWN[key]).total_seconds() > 1.0:
                                ALARM_COOLDOWN[key] = ts
                                if is_breach:
                                    print(f"  [BREACH] {cam.id} {obj.track_id} ({obj.object_type}) inside fence — alarming + snapshot")
                                if is_wanted:
                                    print(f"  [WATCHLIST-ALARM] {cam.id} {obj.track_id} plate {obj.attributes.get('plate_no')} — alarming + snapshot")
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
            grid_idx = {cid: n for n, cid in enumerate(grid_cams)}

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
                        plate_no = obj.attributes.get("plate_no", "")
                        is_wanted = bool(obj.attributes.get("watchlist_match"))

                        if is_wanted:
                            color = (0, 0, 255)  # RED — wanted vehicle
                        elif identity != "Unknown" and not activity and not is_breach:
                            color = (0, 255, 0)
                        elif is_breach or activity:
                            color = (0, 0, 255) # RED
                        else:
                            color = (255, 0, 0) if obj.object_type == "vehicle" else (0, 255, 0)

                        track_num = obj.track_id.split("-")[-1]

                        if is_wanted and plate_no:
                            base = f"WANTED [{plate_no}]"
                        elif identity != "Unknown":
                            base = f"[{identity} | Badge: {badge}]" if badge else f"[{identity}]"
                        elif plate_no:
                            base = f"{obj.object_type.capitalize()} {track_num} [{plate_no}]"
                        else:
                            base = f"{obj.object_type.capitalize()} {track_num}"

                        # Draw the person's photo next to the bounding box if matched.
                        # Thumbnail is cached in memory (loaded from disk once),
                        # so this costs a memcpy instead of imread+resize.
                        if identity != "Unknown" and img_path:
                            try:
                                local_path = _resolve_face_path(img_path)
                                person_img = _get_person_thumb(local_path) if local_path else None
                                if person_img is not None:
                                    fh, fw = display.shape[:2]
                                    size = _THUMB_SIZE
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
                        if is_wanted:
                            tags.append("WANTED")
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

                # Grid cell (grid buffer is preallocated; CUDA probe is hoisted).
                if cam.id in grid_cams:
                    g_idx = grid_idx.get(cam.id)
                    r, c = divmod(g_idx, cols)
                    if r < rows:
                        if _CV2_CUDA:
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

