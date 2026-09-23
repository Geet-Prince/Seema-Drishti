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
            
    def _init_model(self):
        # We use a fast, lightweight insightface setup suitable for edge processing.
        # Try CUDA first to prevent CPU bottlenecking, fallback to CPU.
        self.app = FaceAnalysis(name='buffalo_s', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        # FIX: Use det_size=(320, 320) instead of (640, 640) — the input to this model is
        # already a tight head crop (~100–200 px wide), so 640 is wasteful and can cause
        # insightface to time-out or OOM on dense crowd frames.
        self.app.prepare(ctx_id=0, det_size=(320, 320))

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
        self.index = faiss.IndexFlatIP(dim)  # Inner product (cosine sim for normalized vectors)
        
        embeddings = []
        for i, person in enumerate(personnel):
            emb = np.array(person['embedding'], dtype=np.float32)
            # Normalize embedding for Cosine Similarity
            faiss.normalize_L2(emb.reshape(1, -1))
            embeddings.append(emb)
            self.personnel_map[i] = person
            
        matrix = np.vstack(embeddings)
        self.index.add(matrix)
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
            return  # Already recognized
            
        # FIX: Guard against crops that are too small for insightface to process —
        # this is the primary crash source when many tiny detections appear in crowd scenes.
        if image_crop is None or image_crop.size == 0:
            return
        h_crop, w_crop = image_crop.shape[:2]
        if h_crop < 20 or w_crop < 20:
            return
            
        now = time.time()
        last_time = self.last_enqueue.get(track_id, 0.0)
        
        # Throttle to max 3 frames per second per person to prevent CPU starvation
        if now - last_time < 0.33:
            return
            
        attempts = self.track_attempts.get(track_id, 0)
        if attempts > 30:  # 30 attempts at 3 fps = 10 seconds of processing
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
        try:
            faces = self.app.get(image_bgr)
        except Exception:
            return None
        if not faces:
            return None
        # Return the largest face
        faces = sorted(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
        emb = faces[0].embedding
        # FIX: insightface can return None embedding on very poor quality images
        if emb is None:
            return None
        return emb

    def _process_queue(self):
        while self.running:
            try:
                track_id, crop = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # FIX: Wrap the entire processing block in a broad try/except.
            # Previously one bad crop (e.g. an all-black frame from the Tom Holland
            # concert video) could raise an unhandled exception and kill this thread
            # permanently — causing face recognition to silently stop for the rest
            # of the session.
            try:
                if track_id in self.identity_cache:
                    continue

                # Guard: skip degenerate crops that slipped through enqueue_crop
                if crop is None or crop.size == 0:
                    continue
                h_crop, w_crop = crop.shape[:2]
                if h_crop < 20 or w_crop < 20:
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
                    if w < 45 or h < 45:  # Too blurry/small
                        continue
                    # FIX: Skip faces with None embeddings (common in crowd/blurry frames)
                    if f.embedding is None:
                        continue
                    valid_faces.append(f)
                    
                if not valid_faces:
                    continue
                    
                # Take the largest valid face in the crop
                face = sorted(valid_faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)[0]

                # FIX: Explicit None guard on embedding before passing to numpy
                if face.embedding is None:
                    continue

                emb = np.array(face.embedding, dtype=np.float32).reshape(1, -1)
                faiss.normalize_L2(emb)
                
                # Match in FAISS
                if self.index is None:
                    continue
                distances, indices = self.index.search(emb, 1)
                if len(distances) > 0 and len(distances[0]) > 0:
                    dist = distances[0][0]  # Cosine similarity (normalized vectors)
                    idx = indices[0][0]
                    
                    if dist >= self.confidence_threshold:
                        person = self.personnel_map[idx]
                        self.identity_cache[track_id] = person
                        logger.info(f"Matched {track_id} as {person['name']} (Sim: {dist:.2f})")
                    else:
                        logger.debug(f"Face found for {track_id} but no match (Max Sim: {dist:.2f})")

            except Exception as exc:
                # Log and continue — never crash the worker thread on a single bad frame
                logger.warning(f"Face recognition error for track {track_id}: {exc}")
