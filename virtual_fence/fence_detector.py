import json
import numpy as np
import cv2
from pathlib import Path
from contracts.schema import DetectionResult, DetectedObject


class VirtualFence:
    def __init__(self, roi_path=None, frame_w=1280, frame_h=720, cam_id=None, video_name=None):
        self.cam_id = cam_id
        self.video_name = video_name
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.roi_path = roi_path
        if self.roi_path is None:
            if cam_id:
                cam_path = Path(__file__).parent / f"{cam_id}_roi.json"
                if cam_path.exists():
                    self.roi_path = str(cam_path)
            if self.roi_path is None and video_name:
                base_path = Path(__file__).parent / f"{video_name}_roi.json"
                if base_path.exists():
                    self.roi_path = str(base_path)
            if self.roi_path is None:
                if cam_id:
                    self.roi_path = str(Path(__file__).parent / f"{cam_id}_roi.json")
                else:
                    self.roi_path = str(Path(__file__).parent / "roi_config.json")
        self.polygon = []
        self.contour = None
        self.load_config()
        self._inside_frames = {}
        # Hysteresis: require 2 consecutive YOLO hits inside before firing.
        # (YOLO runs every 2nd loop frame, so 2 hits ≈ 4 loop frames ≈ 0.15s.
        # The old value of 5 meant fast walk-throughs never accumulated enough
        # hits on the same track ID to trigger, so crossings were silently lost.)
        self._enter_threshold = 2
        self._grace_frames = 8

    def load_config(self):
        if self.roi_path and Path(self.roi_path).exists():
            with open(self.roi_path, "r") as f:
                config = json.load(f)
            cal_w = config["frame_width"]
            cal_h = config["frame_height"]
            raw_points = config["polygon"]
            sx = self.frame_w / cal_w
            sy = self.frame_h / cal_h
            self.polygon = [(int(x * sx), int(y * sy)) for (x, y) in raw_points]
            self.contour = np.array(self.polygon, dtype="int32")
        else:
            print(f"Warning: ROI config not found at {self.roi_path}")
            self.contour = None

    def update_polygon(self, raw_points):
        if self.roi_path:
            config = {"frame_width": self.frame_w, "frame_height": self.frame_h, "polygon": raw_points}
            with open(self.roi_path, "w") as f:
                json.dump(config, f, indent=2)
        self.polygon = raw_points
        self.contour = np.array(self.polygon, dtype="int32") if self.polygon else None
        self._inside_frames.clear()

    def _get_foot_point(self, bbox):
        x1, y1, x2, y2 = bbox
        return int((x1 + x2) / 2), int(y2)

    def _get_centroid(self, bbox):
        x1, y1, x2, y2 = bbox
        return int((x1 + x2) / 2), int((y1 + y2) / 2)

    def _point_inside(self, pt):
        if self.contour is None or len(self.contour) < 3:
            return False
        result = cv2.pointPolygonTest(self.contour, (float(pt[0]), float(pt[1])), measureDist=False)
        return result >= 0

    def is_inside(self, bbox, object_type="human"):
        # For humans, use foot point to prevent false alarms from leaning over.
        # For vehicles, use the centroid since their bounding boxes are massive 
        # and their "foot point" is the rear bumper which enters late.
        if object_type == "vehicle":
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            return self._point_inside((cx, cy))
        return self._point_inside(self._get_foot_point(bbox))

    def process(self, result):
        contour = self.contour
        if contour is None or len(contour) < 3 or contour.size == 0:
            return result
        
        current_ids = set()
        for obj in result.objects:
            if obj.object_type not in ("human", "vehicle"):
                continue
            
            track_id = obj.track_id
            current_ids.add(track_id)
            
            physically_inside = self.is_inside(obj.bbox, obj.object_type)
            
            # State is a dict: {"val": int, "active": bool}
            state = self._inside_frames.get(track_id, {"val": 0, "active": False})
            
            if physically_inside:
                state["val"] += (2 if obj.object_type == "vehicle" else 1)
            else:
                state["val"] -= (2 if obj.object_type == "vehicle" else 1)
                
            # Clamp the accumulator
            state["val"] = max(-self._grace_frames, min(self._enter_threshold, state["val"]))
            
            # Hysteresis trigger
            if state["val"] >= self._enter_threshold:
                state["active"] = True
            elif state["val"] <= -self._grace_frames:
                state["active"] = False
                
            self._inside_frames[track_id] = state
            
            if state["active"]:
                obj.attributes["zone_state"] = "inside"
                obj.attributes["zone_id"] = "border_fence"
                
        # Cleanup stale tracks
        expired = [tid for tid in self._inside_frames.keys() if tid not in current_ids]
        for tid in expired:
            del self._inside_frames[tid]
            
        return result

    def draw_fence(self, frame, breach_active=False):
        contour = self.contour
        if contour is None or len(contour) < 3:
            return
        # Ensure contour is valid for OpenCV drawing (needs shape (N, 2) or (N, 1, 2) with N >= 3)
        if contour.size == 0 or len(contour.shape) < 2 or contour.shape[-1] != 2:
            return
            
        if breach_active:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [contour], (0, 0, 255))
            cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
            
            cx = int(contour[:, 0].mean())
            cy = int(contour[:, 1].mean())
            cv2.putText(frame, "RESTRICTED ZONE", (cx - 80, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2, cv2.LINE_AA)
        
        # Always draw the outline and vertices
        cv2.polylines(frame, [contour], isClosed=True, color=(0, 0, 255), thickness=3)
        for pt in contour:
            cv2.circle(frame, (int(pt[0]), int(pt[1])), 5, (0, 80, 255), -1)
