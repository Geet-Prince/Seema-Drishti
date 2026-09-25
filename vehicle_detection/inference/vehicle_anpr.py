"""
Vehicle Detection & ANPR Module - Integrated with IBVAP AlarmManager pipeline
"""
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False

from contracts.schema import DetectionResult, DetectedObject

logger = logging.getLogger(__name__)


def get_best_device():
    """Back-compat wrapper — resolves via configs/compute.py when available."""
    try:
        from configs.compute import detect_compute
        return detect_compute()["device"]
    except Exception:
        pass
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


class VehicleANPR:
    def __init__(self, vehicle_model="yolov8n.pt", plate_model="best.pt"):
        if not _YOLO_AVAILABLE:
            raise RuntimeError("Ultralytics YOLO not installed")
            
        self.device = get_best_device()
        try:
            from configs.compute import apply_torch_thread_limits
            apply_torch_thread_limits()
        except Exception:
            pass
        self.vehicle_model = YOLO(vehicle_model)
        self.vehicle_model.to(self.device)
        
        # Load plate model if it exists, otherwise disable ANPR
        self.plate_model = None
        if Path(plate_model).exists():
            self.plate_model = YOLO(plate_model)
            self.plate_model.to(self.device)
        else:
            logger.warning(f"Plate model {plate_model} not found. ANPR disabled, running vehicle tracking only.")

    def process(self, frame: np.ndarray, camera_id: str, frame_id: int, timestamp: datetime) -> DetectionResult:
        result = DetectionResult(
            module="vehicle_detection",
            camera_id=camera_id,
            frame_id=frame_id,
            timestamp_utc=timestamp,
            objects=[]
        )

        # Classes: 2: car, 3: motorcycle, 5: bus, 7: truck
        is_cuda = str(self.device).startswith("cuda")
        results = self.vehicle_model.track(
            frame,
            persist=True,
            classes=[2, 3, 5, 7],
            verbose=False,
            device=self.device,
            half=is_cuda
        )
        
        if results and len(results) > 0 and results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)
            confidences = results[0].boxes.conf.cpu().numpy()
            class_ids = results[0].boxes.cls.cpu().numpy().astype(int)
            
            # Class mapping
            class_map = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

            for box, track_id, conf, cls_id in zip(boxes, track_ids, confidences, class_ids):
                x1, y1, x2, y2 = box
                # Ensure within frame bounds
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
                
                v_type = class_map.get(cls_id, "vehicle")
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                
                attributes = {
                    "vehicle_type": v_type,
                    "centroid": (cx, cy)
                }
                
                # Run ANPR on the cropped vehicle
                if self.plate_model is not None:
                    roi = frame[y1:y2, x1:x2]
                    if roi.size > 0:
                        plate_results = self.plate_model(roi, verbose=False, device=self.device)
                        if plate_results and len(plate_results) > 0 and plate_results[0].boxes:
                            # If multiple plates found, just take the highest confidence one
                            best_plate_conf = 0
                            for p_box, p_conf in zip(plate_results[0].boxes.xyxy.cpu().numpy(), plate_results[0].boxes.conf.cpu().numpy()):
                                if p_conf > best_plate_conf:
                                    best_plate_conf = float(p_conf)
                                    # In a full ANPR system we would run OCR here (Tesseract / EasyOCR)
                                    # For now, we mock the read plate or just tag that a plate was detected
                                    attributes["plate_no"] = f"DETECTED-{int(best_plate_conf*100)}"
                
                obj = DetectedObject(
                    object_type="vehicle",
                    track_id=f"veh-{track_id}",
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                    confidence=float(conf),
                    attributes=attributes
                )
                result.objects.append(obj)
                
        return result
