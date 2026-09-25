"""
alarm_manager/src/incident_store.py
Manages per-incident folders with full JSON metadata + snapshots.
Owner: Prince
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import cv2
import numpy as np

_INCIDENT_ROOT = Path(__file__).resolve().parents[2] / "storage" / "incidents"


def _incident_dir(incident_id: str, camera_id: str) -> Path:
    d = _INCIDENT_ROOT / camera_id / incident_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_path(incident_id: str, camera_id: str) -> Path:
    return _incident_dir(incident_id, camera_id) / "incident.json"


def load_or_create(incident_id: str, camera_id: str, module: str,
                   danger_score: int, danger_label: str) -> dict:
    path = _meta_path(incident_id, camera_id)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {
        "incident_id": incident_id,
        "camera_id": camera_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "danger_score": danger_score,
        "danger_label": danger_label,
        "modules_triggered": [],
        "humans_detected": 0,
        "faces_captured": 0,
        "vehicles_detected": 0,
        "vehicle_types": [],
        "weapons_detected": 0,
        "track_ids": [],
        "zone_breaches": [],
        "activities_detected": [],
        "plate_numbers": [],
        "watchlist_hits": [],
        "driver_snapshot_count": 0,
        "driver_snapshots": [],
        "snapshot_count": 0,
        "snapshots": [],
        "last_snapshot_at": None,
        "confidence": 0.0,
    }


def save(incident_id: str, meta: dict) -> None:
    meta["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(_meta_path(incident_id, meta["camera_id"]), "w") as f:
        json.dump(meta, f, indent=2)


def add_snapshot(incident_id: str, frame: np.ndarray,
                 bbox: tuple, meta: dict) -> Optional[str]:
    """
    Crop bbox from frame and save inside the incident folder.
    Returns relative filename or None on failure.
    """
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    pad_x = int((x2 - x1) * 0.15)
    pad_y = int((y2 - y1) * 0.15)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    seq = meta["snapshot_count"] + 1
    filename = f"snapshot_{seq:03d}.jpg"
    # Quality 90: visually identical evidence crops at ~30% faster JPEG encode
    # than 95. Evidence bytes only — inference input is untouched.
    cv2.imwrite(str(_incident_dir(incident_id, meta["camera_id"]) / filename), crop,
                [cv2.IMWRITE_JPEG_QUALITY, 90])
    meta["snapshot_count"] = seq
    meta["snapshots"].append(filename)
    meta["last_snapshot_at"] = datetime.now(timezone.utc).isoformat()
    return filename


def add_driver_snapshot(incident_id: str, frame: np.ndarray,
                        vehicle_bbox: tuple, meta: dict) -> Optional[str]:
    """Crop the likely driver/windshield region of a vehicle and save it.

    Heuristic: driver sits in the upper-middle of the vehicle box, so take
    the top ~50% of the box, padded, as the driver crop. Returns the
    relative filename (driver_NNN.jpg) or None on failure.
    """
    try:
        x1, y1, x2, y2 = [int(v) for v in vehicle_bbox]
    except Exception:
        return None
    h, w = frame.shape[:2]
    bw, bh = x2 - x1, y2 - y1
    if bw <= 0 or bh <= 0:
        return None
    # Upper half + slight upward expansion (windshield band), side padding.
    pad_x = int(bw * 0.10)
    dx1 = max(0, x1 - pad_x)
    dx2 = min(w, x2 + pad_x)
    dy1 = max(0, y1 - int(bh * 0.15))
    dy2 = min(h, y1 + int(bh * 0.55))
    if dx2 - dx1 < 20 or dy2 - dy1 < 20:
        return None
    crop = frame[dy1:dy2, dx1:dx2]
    if crop.size == 0:
        return None

    seq = int(meta.get("driver_snapshot_count", 0)) + 1
    filename = f"driver_{seq:03d}.jpg"
    cv2.imwrite(str(_incident_dir(incident_id, meta["camera_id"]) / filename), crop,
                [cv2.IMWRITE_JPEG_QUALITY, 90])
    meta["driver_snapshot_count"] = seq
    meta.setdefault("driver_snapshots", []).append(filename)
    # Also list in snapshots so generic galleries/PDFs pick it up.
    if filename not in meta["snapshots"]:
        meta["snapshots"].append(filename)
    return filename


def enrich_meta(meta: dict, module: str, obj_attributes: dict,
                obj_type: str, track_id: str, danger_score: int,
                danger_label: str, frame_humans: int = 0, frame_vehicles: int = 0,
                confidence: float = 0.0) -> None:
    """Pull all useful fields from a DetectedObject into the incident metadata."""
    if module not in meta["modules_triggered"]:
        meta["modules_triggered"].append(module)

    if danger_score > meta["danger_score"]:
        meta["danger_score"] = danger_score
        meta["danger_label"] = danger_label

    if track_id not in meta["track_ids"]:
        meta["track_ids"].append(track_id)
        
    if confidence > meta.get("confidence", 0.0):
        meta["confidence"] = confidence

    if frame_humans > meta.get("humans_detected", 0):
        meta["humans_detected"] = frame_humans
    if frame_vehicles > meta.get("vehicles_detected", 0):
        meta["vehicles_detected"] = frame_vehicles

    # Enrich from module-specific attributes
    if "zone_id" in obj_attributes and obj_attributes.get("zone_state") == "inside":
        zone = obj_attributes["zone_id"]
        if zone not in meta["zone_breaches"]:
            meta["zone_breaches"].append(zone)

    if "activity" in obj_attributes:
        act = obj_attributes["activity"]
        if act not in meta["activities_detected"]:
            meta["activities_detected"].append(act)

    if "plate_no" in obj_attributes:
        plate = obj_attributes["plate_no"]
        if plate not in meta["plate_numbers"]:
            meta["plate_numbers"].append(plate)
        if obj_attributes.get("watchlist_match") and plate not in meta.get("watchlist_hits", []):
            meta.setdefault("watchlist_hits", []).append(plate)

    if obj_attributes.get("weapon_detected"):
        meta["weapons_detected"] += 1

    if obj_attributes.get("face_captured"):
        meta["faces_captured"] += 1

    if "vehicle_type" in obj_attributes:
        v_type = obj_attributes["vehicle_type"]
        if v_type not in meta["vehicle_types"]:
            meta["vehicle_types"].append(v_type)


def get_all_incidents(limit: int = 100) -> list[dict]:
    """Return most recent incident metadata dicts, sorted by last_updated desc."""
    incidents = []
    if not _INCIDENT_ROOT.exists():
        return incidents
    
    # We now have _INCIDENT_ROOT / <camera_id> / <incident_id> / incident.json
    all_meta_files = list(_INCIDENT_ROOT.rglob("incident.json"))
    
    # Sort by modification time desc
    all_meta_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    for meta_file in all_meta_files[:limit]:
        try:
            with open(meta_file) as f:
                incidents.append(json.load(f))
        except Exception:
            pass
    return incidents
