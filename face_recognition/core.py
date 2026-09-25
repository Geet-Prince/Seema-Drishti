import queue
import threading
import time
import logging
import numpy as np
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# To prevent crashing if not installed, we fallback safely.
try:
    from insightface.app import FaceAnalysis
    import faiss
    _MODULE_AVAILABLE = True
except ImportError:
    _MODULE_AVAILABLE = False
    logger.warning("Face recognition modules (insightface, faiss) not found. Face matching will be disabled.")


def resolve_known_face_path(web_path: str | None) -> str | None:
    """Map a `/storage/...` web path to an absolute file path.

    Checks the live repo storage first (`<ibvap>/storage/...`), then the
    legacy location (`<projects>/storage/...`) so faces uploaded by older
    builds still resolve for the pipeline thumbnail overlay.
    """
    if not web_path:
        return None
    try:
        from pathlib import Path as _P
        rel = web_path.split("/storage/", 1)[-1] if "/storage/" in web_path else web_path.lstrip("/")
        candidates = [
            _P(__file__).resolve().parents[1] / "storage" / rel,  # <ibvap>/storage/...
            _P(__file__).resolve().parents[2] / "storage" / rel,  # <projects>/storage/... (legacy)
        ]
        for c in candidates:
            if c.exists():
                return str(c)
    except Exception:
        pass
    return None


def _personnel_version() -> tuple[int, int]:
    """Cheap (count, max_id) signature of the known_personnel table.

    Used to detect newly added faces without reloading embeddings every time.
    """
    try:
        import sqlite3
        from pathlib import Path as _P
        db = _P(__file__).resolve().parents[1] / "storage" / "events.db"
        if not db.exists():
            return (0, 0)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM known_personnel").fetchone()
            return (int(row[0] or 0), int(row[1] or 0))
        finally:
            conn.close()
    except Exception:
        return (0, 0)


class FaceRecognitionWorker:
    def __init__(self, confidence_threshold=0.48):
        self.confidence_threshold = confidence_threshold
        self.task_queue = queue.Queue(maxsize=100)
        
        # identity_cache[track_id] = {"name": "Omkar", "badge": "123", "image_path": "..."}
        self.identity_cache: Dict[str, dict] = {}
        self.track_attempts: Dict[str, int] = {}
        self.last_enqueue: Dict[str, float] = {}
        
        self.app = None
        self.index = None
        self.personnel_map = {}  # idx -> dict info
        
        self.running = False
        self.worker_thread = None

        if _MODULE_AVAILABLE:
            self._init_model()
            self.reload_database()
            try:
                self._db_version = _personnel_version()
            except Exception:
                self._db_version = (0, 0)
            self._last_reload_check = time.time()
            
    def _init_model(self):
        # Shared provider ordering: TensorRT -> CUDA -> CoreML -> CPU.
        # Works on NVIDIA (TRT/CUDA acceleration) and MacBook (CoreML),
        # falling back to CPU anywhere. Never hardcode a single provider.
        try:
            from configs.compute import resolve_onnx_providers
            providers, ctx_id = resolve_onnx_providers()
        except Exception:
            providers, ctx_id = ['CPUExecutionProvider'], -1
            try:
                import torch
                if torch.cuda.is_available():
                    providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                    ctx_id = 0
            except ImportError:
                pass
            try:
                import onnxruntime
                if 'CoreMLExecutionProvider' in onnxruntime.get_available_providers():
                    providers.insert(0, 'CoreMLExecutionProvider')
            except ImportError:
                pass

        self.app = FaceAnalysis(name='buffalo_s', providers=providers)
        self.app.prepare(ctx_id=ctx_id, det_size=(640, 640))

    def reload_database(self):
        """Loads all known personnel from SQLite and builds the FAISS index."""
        if not _MODULE_AVAILABLE:
            return
            
        import sys
        from pathlib import Path
        db_path = Path(__file__).resolve().parents[2]
        if str(db_path) not in sys.path:
            sys.path.insert(0, str(db_path))
            
        from alarm_manager.src.database import get_all_known_personnel
        personnel = get_all_known_personnel()
        
        if not personnel:
            self.index = None
            self.personnel_map = {}
            return
            
        # Extract embeddings and build index
        dim = len(personnel[0]['embedding'])
        self.index = faiss.IndexFlatIP(dim) # Inner product (cosine sim for normalized vectors)
        
        embeddings = []
        for i, person in enumerate(personnel):
            emb = np.array(person['embedding'], dtype=np.float32)
            # Normalize embedding for Cosine Similarity
            faiss.normalize_L2(emb.reshape(1, -1))
            embeddings.append(emb)
            self.personnel_map[i] = person
            
        matrix = np.vstack(embeddings)
        self.index.add(matrix)
        try:
            self._db_version = _personnel_version()
            self._last_reload_check = time.time()
        except Exception:
            pass
        logger.info(f"Loaded {len(personnel)} face(s) into FAISS index.")

    def start(self):
        if not _MODULE_AVAILABLE:
            return
        self.running = True
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0)

    def enqueue_crop(self, track_id: str, image_crop: np.ndarray):
        """Enqueue a face crop. Fails silently if queue is full."""
        if not _MODULE_AVAILABLE or self.index is None:
            return
            
        if track_id in self.identity_cache:
            return # Already recognized
            
        now = time.time()
        last_time = self.last_enqueue.get(track_id, 0.0)
        
        # Throttle to max 3 frames per second per person to prevent CPU starvation
        if now - last_time < 0.33:
            return
            
        attempts = self.track_attempts.get(track_id, 0)
        if attempts > 30: # 30 attempts at 3 fps = 10 seconds of processing!
            return 
            
        try:
            self.task_queue.put_nowait((track_id, image_crop))
            self.track_attempts[track_id] = attempts + 1
            self.last_enqueue[track_id] = now
        except queue.Full:
            pass

    def get_identity(self, track_id: str) -> Optional[dict]:
        return self.identity_cache.get(track_id)

    def extract_embedding(self, image_bgr: np.ndarray) -> Optional[np.ndarray]:
        """Extract a single face embedding from an image. Used by API when registering new personnel."""
        if not self.app:
            return None
        faces = self.app.get(image_bgr)
        if not faces:
            return None
        # Return the largest face
        faces = sorted(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
        return faces[0].embedding

    def _process_queue(self):
        while self.running:
            # Hot-reload newly enrolled faces without a pipeline restart.
            # The upload API inserts into SQLite from another thread/process,
            # so poll a cheap (count, max_id) signature every ~10s.
            try:
                now = time.time()
                if now - getattr(self, '_last_reload_check', 0) > 10.0:
                    self._last_reload_check = now
                    if _personnel_version() != getattr(self, '_db_version', (0, 0)):
                        logger.info("New personnel detected — reloading face database.")
                        self.reload_database()
            except Exception:
                pass
            try:
                track_id, crop = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self.index is None:
                continue
                
            if track_id in self.identity_cache:
                continue
                
            faces = self.app.get(crop)
            if not faces:
                continue
                
            # Filter faces by detection confidence and size to prevent garbage embeddings
            valid_faces = []
            for f in faces:
                if getattr(f, 'det_score', 0) < 0.6:
                    continue
                w, h = f.bbox[2] - f.bbox[0], f.bbox[3] - f.bbox[1]
                if w < 45 or h < 45: # Too blurry/small
                    continue
                valid_faces.append(f)
                
            if not valid_faces:
                continue
                
            # Take the largest valid face in the crop
            face = sorted(valid_faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)[0]
            emb = np.array(face.embedding, dtype=np.float32).reshape(1, -1)
            faiss.normalize_L2(emb)
            
            # Match in FAISS
            distances, indices = self.index.search(emb, 1)
            if len(distances) > 0 and len(distances[0]) > 0:
                dist = distances[0][0] # Since vectors are normalized, this is cosine similarity
                idx = indices[0][0]
                
                if dist >= self.confidence_threshold:
                    person = self.personnel_map[idx]
                    self.identity_cache[track_id] = person
                    logger.info(f"Matched {track_id} as {person['name']} (Sim: {dist:.2f})")
                else:
                    logger.debug(f"Face found for {track_id} but no match (Max Sim: {dist:.2f})")
