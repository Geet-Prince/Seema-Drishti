"""
alarm_manager/src/frame_buffer.py
Thread-safe global frame store — shared between camera loop and MJPEG stream.
Supports per-camera individual streams + combined grid stream.
Owner: Prince
"""
from __future__ import annotations
import threading
import time
import cv2
import numpy as np
from typing import Optional, Dict


class FrameBuffer:
    """Stores the latest JPEG frame bytes for MJPEG streaming."""

    def __init__(self, fps_limit: float = 12.0):
        self._lock = threading.Lock()
        self._frame_bytes: Optional[bytes] = None
        self._updated_at: float = 0.0
        self._fps_limit = fps_limit
        self._pending = None  # latest in-flight encode future (or None)

    def write(self, frame: np.ndarray) -> None:
        """Call this from the camera loop with every raw BGR frame."""
        now = time.time()
        # Throttle JPEG encoding to save CPU (e.g., max 12 FPS)
        if now - self._updated_at < (1.0 / self._fps_limit):
            return
        self._updated_at = now

        if getattr(self, '_pool', None) is None:
            from concurrent.futures import ThreadPoolExecutor
            self._pool = ThreadPoolExecutor(max_workers=1)

        # Drop the frame if the encoder is still busy with the previous one.
        # Without this, a slow encoder queues stale frames: latency and memory
        # grow while the dashboard falls further behind live. Display-only, so
        # skipping changes nothing about detection accuracy.
        pending = self._pending
        if pending is not None and not pending.done():
            return
        # Encode a private copy: the caller reuses/mutates its array after
        # write() returns, which would otherwise corrupt the async encode.
        self._pending = self._pool.submit(self._encode_async, frame.copy())

    def _encode_async(self, frame: np.ndarray) -> None:
        # Lower quality = much faster CPU encode
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
        with self._lock:
            self._frame_bytes = buf.tobytes()

    def read(self) -> Optional[bytes]:
        with self._lock:
            return self._frame_bytes

    def is_fresh(self, max_age_s: float = 3.0) -> bool:
        return (time.time() - self._updated_at) < max_age_s


class CameraBufferRegistry:
    """Manages per-camera frame buffers + the combined grid buffer."""

    def __init__(self):
        self._lock = threading.Lock()
        self._buffers: Dict[str, FrameBuffer] = {}
        self.grid = FrameBuffer(fps_limit=15.0)  # slightly higher limit for grid
        self._camera_meta: Dict[str, dict] = {}
        self._live_counts: Dict[str, int] = {}
        self._frame_id: int = 0
        self.active_ai_cam: Optional[str] = None

    def set_ai_cam(self, cam_id: str) -> None:
        with self._lock:
            if cam_id in self._buffers:
                self.active_ai_cam = cam_id

    def register(self, cam_id: str, name: str = "", source: str = "") -> FrameBuffer:
        with self._lock:
            if cam_id not in self._buffers:
                self._buffers[cam_id] = FrameBuffer()
                self._camera_meta[cam_id] = {
                    "id": cam_id,
                    "name": name or cam_id,
                    "source": source,
                    "status": "online"
                }
                if self.active_ai_cam is None:
                    self.active_ai_cam = cam_id
            return self._buffers[cam_id]

    def get(self, cam_id: str) -> Optional[FrameBuffer]:
        with self._lock:
            return self._buffers.get(cam_id)

    def update_live(self, cam_id: str, obj_count: int, frame_id: int):
        with self._lock:
            self._live_counts[cam_id] = obj_count
            self._frame_id = frame_id

    def get_cameras(self) -> list:
        with self._lock:
            result = []
            for cam_id, meta in self._camera_meta.items():
                buf = self._buffers.get(cam_id)
                entry = dict(meta)
                entry["online"] = buf.is_fresh(5.0) if buf else False
                entry["objects"] = self._live_counts.get(cam_id, 0)
                result.append(entry)
            return result

    def get_live_info(self) -> dict:
        with self._lock:
            total = sum(self._live_counts.values())
            return {
                "humans": total,
                "frame_id": self._frame_id,
                "updated_at": time.time(),
                "live": any(b.is_fresh(3.0) for b in self._buffers.values()),
                "cameras": len(self._buffers),
            }


# Singletons
LIVE_FRAME = FrameBuffer()       # backward compat
CAMERA_REGISTRY = CameraBufferRegistry()
