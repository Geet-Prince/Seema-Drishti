"""
human_detection/inference/detector.py
=======================================
THE PUBLIC API for the Human Detection module.

This is the only file other modules (or the Video Input Layer) should ever import.

Architecture contract:
  - Input:  a raw BGR numpy frame (from OpenCV / RTSP)
  - Output: DetectionResult with module="human_detection"
  - The caller (video_input.py or a test) is responsible for calling
    alarm_manager.submit(result). This class ONLY detects — it never
    writes files, saves to DB, or sends alerts.

Owner: Prince
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

# Lazy import of ultralytics — lets unit tests run without a GPU/model file
# by using the mock path in testing/test_detector.py
try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False

from contracts import DetectedObject, DetectionResult

logger = logging.getLogger(__name__)

# Paths relative to the human_detection/ folder
_MODULE_DIR = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _MODULE_DIR / "configs" / "config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


class HumanDetector:
    """
    Wraps a YOLO model to detect humans in a single video frame.

    Usage
    -----
    >>> detector = HumanDetector()
    >>> result = detector.detect(frame, camera_id="CAM_01", frame_id=42)
    >>> alarm_manager.submit(result)

    The detector loads weights lazily on first call to detect() so that
    instantiation is cheap and test setups don't need a real GPU/model.

    Parameters
    ----------
    config_override : dict, optional
        Override any config key at runtime (useful in tests).
    """

    def __init__(self, config_override: Optional[dict] = None):
        cfg = _load_config()
        if config_override:
            # Deep-merge overrides
            for key, value in config_override.items():
                if isinstance(value, dict) and key in cfg:
                    cfg[key].update(value)
                else:
                    cfg[key] = value

        self._cfg = cfg
        self._model: Optional[object] = None  # loaded lazily

    # ── Private helpers ──────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Load YOLO weights. Called once, on the first detect() call."""
        if not _YOLO_AVAILABLE:
            raise RuntimeError(
                "ultralytics is not installed. Run: pip install ultralytics"
            )

        weights_path = _MODULE_DIR / self._cfg["model"]["weights"]
        if not weights_path.exists():
            fallback = self._cfg["model"]["pretrained_fallback"]
            logger.warning(
                "Weights not found at %s — downloading pretrained '%s'.",
                weights_path,
                fallback,
            )
            self._model = YOLO(fallback)
            # Save to the expected location so future runs are fast
            weights_path.parent.mkdir(parents=True, exist_ok=True)
            self._model.save(str(weights_path))
            pt_file = str(weights_path)
        else:
            logger.info("Loading weights from %s", weights_path)
            pt_file = str(weights_path)

        # macOS: prefer the Apple Neural Engine build of this exact .pt
        # (FP32 export, same weights/post-processing — no accuracy change).
        # Builds once on first run; falls back to PyTorch on any failure.
        try:
            import platform as _plat
            if _plat.system() == "Darwin":
                from configs.compute import ensure_coreml_model
                cm = ensure_coreml_model(pt_file)
                if cm != pt_file:
                    logger.info("Loading CoreML model from %s", cm)
                    self._model = YOLO(cm)
                    return
        except Exception as exc:
            logger.warning("CoreML path unavailable (%s); using PyTorch.", exc)

        if self._model is None:
            self._model = YOLO(pt_file)

    def _run_inference(self, frame: np.ndarray) -> list[dict]:
        """
        Run YOLO on a single BGR frame.

        Returns a list of raw detection dicts:
            [{"bbox": (x1, y1, x2, y2), "confidence": float}, ...]
        Only class 0 (person) detections are returned.
        """
        target_classes: list[int] = self._cfg["model"]["target_classes"]
        conf_thresh: float = self._cfg["model"]["confidence_threshold"]
        iou_thresh: float = self._cfg["model"]["iou_threshold"]
        # Auto-switch compute backend (NVIDIA TensorRT/CUDA <-> Apple CPU).
        # "auto" (or legacy unset) resolves via configs/compute.py; explicit
        # "cpu"/"cuda:0"/"mps" values are honored. FP16 is enabled for real
        # CUDA only — half=True on CPU/MPS is slower or errors out.
        try:
            from configs.compute import resolve_yolo_settings
            yolo_cfg = resolve_yolo_settings(self._cfg["model"].get("device"))
        except Exception:
            yolo_cfg = {"device": self._cfg["model"].get("device") or "cpu",
                        "half": False, "imgsz": 640}
        device: str = yolo_cfg["device"]

        results = self._model.predict(
            source=frame,
            classes=target_classes,
            conf=conf_thresh,
            iou=iou_thresh,
            device=device,
            imgsz=yolo_cfg["imgsz"],
            verbose=False,
            half=yolo_cfg["half"],
        )

        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                detections.append({
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                    "confidence": round(conf, 4),
                })
        return detections

    # ── Public API ───────────────────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        camera_id: str,
        frame_id: int,
        timestamp_utc: Optional[datetime] = None,
    ) -> DetectionResult:
        """
        Detect humans in a single BGR video frame.

        Parameters
        ----------
        frame        : BGR numpy array (H, W, 3) from OpenCV
        camera_id    : e.g. "CAM_01" — must match configs/system.yaml
        frame_id     : monotonically increasing frame counter
        timestamp_utc: UTC datetime of the frame; defaults to now()

        Returns
        -------
        DetectionResult  — ready to pass to alarm_manager.submit()
        """
        if self._model is None:
            self._load_model()

        if timestamp_utc is None:
            timestamp_utc = datetime.now(timezone.utc)

        raw_detections = self._run_inference(frame)

        prefix: str = self._cfg["output"]["track_id_prefix"]
        objects = [
            DetectedObject(
                object_type="human",
                # Temporary track_id — Human Tracking will replace this with
                # a stable ID. Format: "det-<frame_id>-<idx>"
                track_id=f"{prefix}-{frame_id}-{idx}",
                confidence=det["confidence"],
                bbox=det["bbox"],
                attributes={},
            )
            for idx, det in enumerate(raw_detections)
        ]

        return DetectionResult(
            module="human_detection",
            camera_id=camera_id,
            frame_id=frame_id,
            timestamp_utc=timestamp_utc,
            objects=objects,
        )

    def benchmark(self, frame: np.ndarray, runs: int = 50) -> dict:
        """
        Measure average inference latency over `runs` frames.

        Useful before demo day to confirm the pipeline meets real-time requirements.

        Returns
        -------
        dict with keys: runs, avg_ms, min_ms, max_ms, fps
        """
        if self._model is None:
            self._load_model()

        latencies = []
        for _ in range(runs):
            t0 = time.perf_counter()
            self._run_inference(frame)
            latencies.append((time.perf_counter() - t0) * 1000)

        avg = sum(latencies) / len(latencies)
        return {
            "runs": runs,
            "avg_ms": round(avg, 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "fps": round(1000 / avg, 1),
        }
