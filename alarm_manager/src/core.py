"""
alarm_manager/src/core.py  (v2 — with adaptive snapshot rate + incident folders)
Owner: Prince
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from contracts.schema import DetectionResult
from alarm_manager.src.database import init_db, log_activity, log_event
from alarm_manager.src import incident_store

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).resolve().parents[1] / "configs" / "rules.yaml"

# Global WebSocket broadcaster
_alert_subscribers: list = []

def register_subscriber(q: asyncio.Queue) -> None:   _alert_subscribers.append(q)
def unregister_subscriber(q: asyncio.Queue) -> None:
    try: _alert_subscribers.remove(q)
    except ValueError: pass


def _load_rules() -> dict:
    with open(_RULES_PATH) as f:
        return yaml.safe_load(f)


def _danger_label(score: int, t: dict) -> str:
    if score >= t["critical"]: return "CRITICAL"
    if score >= t["high"]:     return "HIGH"
    if score >= t["medium"]:   return "MEDIUM"
    return "LOW"


def _snapshot_interval(score: int) -> float:
    """
    Adaptive snapshot rate — the higher the threat, the faster we capture.
    Score 20-39  → every 2.0 s
    Score 40-59  → every 1.0 s
    Score 60-79  → every 0.5 s
    Score 80+    → every 0.2 s  (near-continuous)
    """
    if score >= 80: return 0.2
    if score >= 60: return 0.5
    if score >= 40: return 1.0
    return 2.0


class AlarmManager:
    def __init__(self):
        init_db()
        cfg = _load_rules()
        self._rules      = cfg["rules"]
        self._thresholds = cfg["thresholds"]
        # track_id → last snapshot unix timestamp
        self._last_snap: dict[str, float] = {}
        self._meta_cache: dict[str, dict] = {}
        self._dirty_meta: set[str] = set()
        self._last_alert: dict[str, float] = {}
        self._last_flush = time.time()
        self._last_known_plates: dict[str, str] = {}
        valid_rules = sum(1 for r in self._rules if r.get("module"))
        logger.info(f"AlarmManager v2 ready. Loaded {len(self._rules)} rules from {_RULES_PATH} (valid modules: {valid_rules}).")

    # ── Public API ──────────────────────────────────────────────────────
    def submit(self, result: DetectionResult,
               frame: Optional[np.ndarray] = None) -> None:
        
        frame_humans = sum(1 for o in result.objects if o.object_type == "human")
        frame_vehicles = sum(1 for o in result.objects if o.object_type == "vehicle")
        
        if not hasattr(self, '_track_start_times'):
            self._track_start_times = {}
        
        current_time = time.time()
        
        for obj in result.objects:
            identity = obj.attributes.get("identity", "Unknown")
            
            # KNOWN personnel should not trigger fence breaches or suspicious activity alarms.
            # We strip these attributes so they only trigger the low-level "Human Tracked" informational log.
            if identity != "Unknown":
                obj.attributes.pop("zone_state", None)
                obj.attributes.pop("activity", None)
            else:
                # For UNKNOWN humans, wait 1.5s before allowing ACTIVITY rules
                # (loitering etc.) so Face Recognition has time to identify them.
                # Fence breaches (zone_state == inside) must NOT be delayed —
                # a fast walk-through would otherwise cross and leave before
                # the gate opens and no alarm/snapshot would ever fire.
                if obj.object_type == "human":
                    zone_breach = obj.attributes.get("zone_state") == "inside"
                    if not zone_breach:
                        start_time = self._track_start_times.get(obj.track_id)
                        if start_time is None:
                            self._track_start_times[obj.track_id] = current_time
                            start_time = current_time

                        if current_time - start_time < 1.5:
                            continue  # Suppress alarms for first 1.5s
                    else:
                        # Breach goes through immediately; seed the timer so a
                        # later activity on the same track is gated correctly.
                        self._track_start_times.setdefault(obj.track_id, current_time)
            
            score, matched_rule = self._score(result.module, obj.attributes, obj.object_type)
            label = matched_rule["severity"].capitalize() if matched_rule else _danger_label(score, self._thresholds)

            # Always log to activity_log
            log_activity(
                camera_id=result.camera_id, module=result.module,
                track_id=obj.track_id, object_type=obj.object_type,
                confidence=obj.confidence, bbox=obj.bbox,
                attributes=obj.attributes, frame_id=result.frame_id,
                score=score,
            )

            incident_id = hashlib.md5(
                f"{result.camera_id}-{obj.track_id}".encode()
            ).hexdigest()[:12]

            # If this is a low-threat event AND we've never created an incident for it, skip.
            # But if it's already an active incident, we must keep enriching it (e.g. for async ANPR plates)
            if score < 30 and not (matched_rule and matched_rule.get("capture_snapshot", False)):
                if incident_id not in self._meta_cache:
                    continue

            effective_module = "vehicle_tracking" if obj.object_type == "vehicle" and result.module == "human_tracking" else result.module

            # Load or create incident metadata
            if incident_id not in self._meta_cache:
                self._meta_cache[incident_id] = incident_store.load_or_create(
                    incident_id, result.camera_id, effective_module, score, label)
            meta = self._meta_cache[incident_id]

            # Enrich metadata with all available signal
            incident_store.enrich_meta(
                meta, effective_module, obj.attributes,
                obj.object_type, obj.track_id, score, label,
                frame_humans, frame_vehicles, obj.confidence)

            plate_no = obj.attributes.get("plate_no")
            if plate_no:
                plate_file = f"plate_{plate_no}.jpg"
                if plate_file not in meta["snapshots"]:
                    meta["snapshots"].append(plate_file)
                    
            # Adaptive snapshot: only capture if enough time has passed
            snapshot_file = None
            should_snapshot = matched_rule.get("capture_snapshot", False) if matched_rule else False
            if frame is not None and should_snapshot:
                interval = _snapshot_interval(score)
                last = self._last_snap.get(obj.track_id, 0.0)
                if time.time() - last >= interval:
                    snapshot_file = incident_store.add_snapshot(
                        incident_id, frame, obj.bbox, meta)
                    self._last_snap[obj.track_id] = time.time()

            # Persist incident JSON only if it has evidence or is a significant threat (>= 30)
            if snapshot_file or meta.get("snapshot_count", 0) > 0 or score >= 30:
                self._dirty_meta.add(incident_id)
                
            # Flush dirty cache periodically (e.g. every 1.5 seconds)
            now = time.time()
            if now - self._last_flush > 1.5 and self._dirty_meta:
                for iid in list(self._dirty_meta):
                    if iid in self._meta_cache:
                        incident_store.save(iid, self._meta_cache[iid])
                self._dirty_meta.clear()
                self._last_flush = now

            if matched_rule:
                plate_no = obj.attributes.get("plate_no")
                is_new_plate = plate_no and self._last_known_plates.get(incident_id) != plate_no
                time_since_last = now - self._last_alert.get(incident_id, 0)
                
                # Broadcast and log ONLY if: it's a new incident (>3s since last alert), 
                # OR we just captured a new snapshot, OR we just detected a new license plate
                if time_since_last > 3.0 or snapshot_file or is_new_plate:
                    if plate_no:
                        self._last_known_plates[incident_id] = plate_no
                    self._last_alert[incident_id] = now
                    
                    log_event(
                        event_id=incident_id,
                        event_type=matched_rule["name"].upper().replace(" ", "_"),
                        severity=matched_rule["severity"],
                        camera_id=result.camera_id,
                        track_id=obj.track_id,
                        danger_score=score,
                        # If no snapshot this frame, don't overwrite with empty in the DB UPSERT, but upsert needs a value.
                        # Wait, we pass the latest snapshot from meta instead of just this frame's snapshot!
                        snapshot_path=meta["snapshots"][-1] if meta["snapshots"] else "",
                        module=effective_module,
                        attributes=obj.attributes,
                    )

                    alert = {
                        "incident_id":    incident_id,
                        "event_type":     matched_rule["name"],
                        "severity":       matched_rule["severity"],
                        "danger_label":   label,
                        "danger_score":   score,
                        "camera_id":      result.camera_id,
                        "track_id":       obj.track_id,
                        "module":         effective_module,
                        "confidence":     obj.confidence,
                        "bbox":           list(obj.bbox),
                        "snapshot":       meta["snapshots"][-1] if meta["snapshots"] else None,
                        "humans_detected": meta["humans_detected"],
                        "zone_breaches":  meta["zone_breaches"],
                        "activities":     meta["activities_detected"],
                        "timestamp":      result.timestamp_utc.isoformat(),
                        "plate_no":       plate_no,
                    }
                    self._broadcast(alert)

    # ── Scoring ─────────────────────────────────────────────────────────
    def _score(self, module: str, attributes: dict, object_type: str = None) -> tuple[int, Optional[dict]]:
        best_rule, best_score = None, 0
        for rule in self._rules:
            if rule.get("module") != module:
                continue
            if "object_type" in rule and rule["object_type"] != object_type:
                continue
            if "attribute" in rule:
                val = attributes.get(rule["attribute"])
                if rule.get("equals") is not None:
                    # Activity can be a comma-joined multi-label string like
                    # "loitering, crowd_formation" — match any single label.
                    if isinstance(val, str) and "," in val:
                        parts = [p.strip() for p in val.split(",")]
                        if rule["equals"] not in parts:
                            continue
                    elif val != rule["equals"]:
                        continue
                if rule.get("gte") is not None and (val is None or val < rule["gte"]):
                    continue
            
            # Map severity to a base score if 'score' isn't provided
            sev = rule.get("severity", "informational").lower()
            score = rule.get("score")
            if score is None:
                if sev == "critical": score = 90
                elif sev == "high": score = 70
                elif sev == "medium": score = 50
                elif sev == "low": score = 30
                else: score = 10
                
            if score > best_score:
                best_score = score
                best_rule  = rule
        return best_score, best_rule

    # ── Broadcast ───────────────────────────────────────────────────────
    def _broadcast(self, alert: dict) -> None:
        for q in list(_alert_subscribers):
            try: q.put_nowait(alert)
            except asyncio.QueueFull: pass
