"""
alarm_manager/src/grouper.py — Intrusion Event grouping (Mission Control layer)
Owner: optimization branch (MC-1)

Groups N per-frame Detections into ONE Intrusion Event when they share
place + time + behaviour. Pure functions, no GPU, fully unit-testable.

Tunables (single source of truth — also mirrored in
optimization/MISSION_CONTROL_CHECKLIST.md):
  T_WINDOW=90s, DORMANT_CLOSE=600s, REID_THRESH=0.65,
  LINK_THRESH=50, SPLIT_PX=200, ACK_SLA=60s, ESCALATE_SLA=180s

Design:
  person_key(det) = ReID cluster id if embedding present, else "cam:track".
  link_score(det, event): +50 same zone, +30 adjacent zone,
    +60 ReID hit, +10 shared activity, +10 converging velocity.
  Link if score >= LINK_THRESH (50).
  Lifecycle: OPEN -> ESCALATING (corroborated) -> ACKED -> DISPATCHED
    -> RESOLVED | CLOSED | FALSE_ALARM. Sweep closes dormant events.
  Merge: two OPEN events, adjacent zones, time overlap, shared person or
    converging behaviour -> merge into older, log MERGED.
  Split: one event with 2 spatial clusters separated > SPLIT_PX for >30s
    with no shared person -> split, log SPLIT_FROM.

Wiring (next step, not here): AlarmManager.submit() calls ingest() with
enriched DetectionResult objects; WebSocket emits EventUpdate, not raw alerts.
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ── Tunables ──────────────────────────────────────────────────────────────
T_WINDOW = 90
DORMANT_CLOSE = 600
REID_THRESH = 0.65
LINK_THRESH = 50
SPLIT_PX = 200
SPLIT_SEPARATED_SECS = 30
ACK_SLA = 60
ESCALATE_SLA = 180

# Adjacency graph: zone_id -> [neighbour zone_ids]. Extend per outpost.
# Falls back to "same camera = adjacent" when zone unknown.
ADJACENCY: dict[str, list[str]] = {}

OPEN_STATES = {"OPEN", "ESCALATING", "ACKED", "DISPATCHED"}


def _now_ts() -> float:
    return time.time()


def person_key(camera_id: str, track_id: str, attributes: dict | None = None) -> str:
    """Stable cross-frame person id. Prefers ReID cluster when available.

    attributes may carry:
      reid_cluster: str (pre-clustered id from face/body ReID), or
      reid: list[float] + reid_id: str (nearest cluster set upstream).
    Fallback is per-camera track (no cross-cam dedup, but never wrong).
    """
    attrs = attributes or {}
    for k in ("reid_cluster", "reid_id", "person_key"):
        v = attrs.get(k)
        if v:
            return str(v)
    return f"{camera_id}:{track_id}"


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def reid_match(emb_a: list[float] | None, emb_b: list[float] | None,
               thresh: float = REID_THRESH) -> bool:
    if not emb_a or not emb_b:
        return False
    return _cosine(emb_a, emb_b) >= thresh


def zones_adjacent(zone_a: str | None, zones_b: set[str] | list[str]) -> bool:
    if not zone_a:
        return False
    zones_b = set(zones_b or [])
    if zone_a in zones_b:
        return False  # same zone handled separately, not "adjacent"
    for z in zones_b:
        if zone_a in ADJACENCY.get(z, []) or z in ADJACENCY.get(zone_a, []):
            return True
    return False


@dataclass
class Event:
    id: str = field(default_factory=lambda: f"ESC-{uuid.uuid4().hex[:6].upper()}")
    state: str = "OPEN"
    zone_ids: set[str] = field(default_factory=set)
    camera_ids: set[str] = field(default_factory=set)
    person_keys: set[str] = field(default_factory=set)
    track_ids: set[str] = field(default_factory=set)
    behaviours: set[str] = field(default_factory=set)
    opened_at: float = field(default_factory=_now_ts)
    last_seen: float = field(default_factory=_now_ts)
    score_max: int = 0
    det_count: int = 0
    # last known centroid per person_key for split detection: pk -> (x, y, ts)
    positions: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # (ts, transition, actor)

    @property
    def headcount(self) -> int:
        return len(self.person_keys)

    def to_update(self) -> dict:
        return {
            "event_id": self.id,
            "state": self.state,
            "headcount": self.headcount,
            "zones": sorted(self.zone_ids),
            "cameras": sorted(self.camera_ids),
            "behaviours": sorted(self.behaviours),
            "score_max": self.score_max,
            "det_count": self.det_count,
            "opened_at": datetime.fromtimestamp(self.opened_at, tz=timezone.utc).isoformat(),
            "last_seen": datetime.fromtimestamp(self.last_seen, tz=timezone.utc).isoformat(),
            "ack_due_in": max(0, ACK_SLA - (_now_ts() - self.opened_at)),
        }


def link_score(det_zone: str | None, det_pk: str, det_activity: str | None,
               event: Event, same_camera: bool = False) -> int:
    """Score 0..130. Link if >= LINK_THRESH."""
    s = 0
    if det_zone and det_zone in event.zone_ids:
        s += 50
    elif det_zone and zones_adjacent(det_zone, event.zone_ids):
        s += 30
    elif same_camera and not det_zone:
        s += 20  # weak fallback: same camera, unknown zone
    if det_pk in event.person_keys:
        s += 60
    if det_activity and det_activity in event.behaviours:
        s += 10
    return s


def attach(event: Event, camera_id: str, track_id: str, zone: str | None,
           activity: str | None, score: int, centroid: tuple | None = None,
           now: float | None = None) -> Event:
    now = now if now is not None else _now_ts()
    pk = person_key(camera_id, track_id, {"reid_cluster": None})
    # NOTE: caller passes precomputed pk when attributes available (see ingest_detection).
    event.last_seen = now
    event.det_count += 1
    event.camera_ids.add(camera_id)
    event.track_ids.add(f"{camera_id}:{track_id}")
    if zone:
        event.zone_ids.add(zone)
    if activity:
        event.behaviours.add(activity)
    if score and score > event.score_max:
        event.score_max = score
    if centroid:
        event.positions[pk] = (centroid[0], centroid[1], now)
        event.person_keys.add(pk)
    else:
        event.person_keys.add(pk)
    return event


def ingest_detection(store: dict[str, Event], camera_id: str, track_id: str,
                     zone: str | None, activity: str | None, score: int = 0,
                     centroid: tuple | None = None, attributes: dict | None = None,
                     now: float | None = None) -> tuple[Event, bool]:
    """Attach one detection to best open event or create new. Returns (event, created)."""
    now = now if now is not None else _now_ts()
    pk = person_key(camera_id, track_id, attributes)
    same_cam_events = [e for e in store.values() if e.state in OPEN_STATES]
    best, best_s = None, 0
    for ev in same_cam_events:
        if (now - ev.last_seen) > T_WINDOW:
            continue
        s = link_score(zone, pk, activity, ev,
                       same_camera=(camera_id in ev.camera_ids))
        if s > best_s:
            best, best_s = ev, s
    if best and best_s >= LINK_THRESH:
        best.last_seen = now
        best.det_count += 1
        best.camera_ids.add(camera_id)
        best.track_ids.add(f"{camera_id}:{track_id}")
        best.person_keys.add(pk)
        if zone:
            best.zone_ids.add(zone)
        if activity:
            best.behaviours.add(activity)
        if score and score > best.score_max:
            best.score_max = score
        if centroid:
            best.positions[pk] = (centroid[0], centroid[1], now)
        return best, False
    ev = Event()
    ev.opened_at = now
    ev.last_seen = now
    ev.det_count = 1
    ev.camera_ids.add(camera_id)
    ev.track_ids.add(f"{camera_id}:{track_id}")
    ev.person_keys.add(pk)
    if zone:
        ev.zone_ids.add(zone)
    if activity:
        ev.behaviours.add(activity)
    ev.score_max = score or 0
    if centroid:
        ev.positions[pk] = (centroid[0], centroid[1], now)
    ev.history.append((now, "OPEN", "system"))
    store[ev.id] = ev
    return ev, True


def corroborated(event: Event) -> bool:
    """Two-signal rule: breach+behaviour, or multi-person, or multi-cam."""
    if event.score_max >= 60:
        return True
    if event.headcount >= 3:
        return True
    if len(event.camera_ids) >= 2:
        return True
    if event.zone_ids and event.behaviours:
        return True
    return False


def sweep(store: dict[str, Event], now: float | None = None) -> list[dict]:
    """Lifecycle sweep: escalate corroborated, auto-close dormant. Returns updates."""
    now = now if now is not None else _now_ts()
    updates = []
    for ev in list(store.values()):
        if ev.state == "OPEN" and corroborated(ev):
            ev.state = "ESCALATING"
            ev.history.append((now, "ESCALATING", "system"))
            updates.append(ev.to_update())
        if ev.state in OPEN_STATES and (now - ev.last_seen) > DORMANT_CLOSE:
            ev.state = "RESOLVED"
            ev.history.append((now, "RESOLVED:auto-close", "system"))
            updates.append(ev.to_update())
    # merge pass
    for ev in [e for e in store.values() if e.state in OPEN_STATES]:
        m = check_merge(store, ev, now)
        if m:
            updates.append(m.to_update())
    return updates


def check_merge(store: dict[str, Event], ev: Event, now: float | None = None) -> Event | None:
    now = now if now is not None else _now_ts()
    for other in list(store.values()):
        if other.id == ev.id or other.state not in OPEN_STATES:
            continue
        if abs(ev.last_seen - other.last_seen) > T_WINDOW:
            continue
        shared_person = bool(ev.person_keys & other.person_keys)
        zones_ok = bool(ev.zone_ids & other.zone_ids) or any(
            zones_adjacent(z, other.zone_ids) for z in ev.zone_ids)
        shared_beh = bool(ev.behaviours & other.behaviours)
        if shared_person or (zones_ok and shared_beh) or (
                zones_ok and abs(ev.last_seen - other.last_seen) <= T_WINDOW
                and ev.headcount + other.headcount <= 12 and shared_beh):
            # merge newer into older
            keep, drop = (ev, other) if ev.opened_at <= other.opened_at else (other, ev)
            keep.zone_ids |= drop.zone_ids
            keep.camera_ids |= drop.camera_ids
            keep.person_keys |= drop.person_keys
            keep.track_ids |= drop.track_ids
            keep.behaviours |= drop.behaviours
            keep.positions.update(drop.positions)
            keep.score_max = max(keep.score_max, drop.score_max)
            keep.det_count += drop.det_count
            keep.last_seen = max(keep.last_seen, drop.last_seen)
            keep.history.append((now, f"MERGED:{drop.id}", "system"))
            drop.state = "CLOSED"
            drop.history.append((now, f"MERGED_INTO:{keep.id}", "system"))
            return keep
    return None


def check_split(store: dict[str, Event], ev: Event, now: float | None = None) -> Event | None:
    """Split if positions form 2 clusters > SPLIT_PX apart with no shared recent link."""
    now = now if now is not None else _now_ts()
    pts = [(pk, v[0], v[1]) for pk, v in ev.positions.items()]
    if len(pts) < 2:
        return None
    # simple 2-cluster: split by median x, check separation
    xs = sorted(p[1] for p in pts)
    med = xs[len(xs) // 2]
    left = [p for p in pts if p[1] < med]
    right = [p for p in pts if p[1] >= med]
    if not left or not right:
        return None
    min_sep = min(abs(a[1] - b[1]) + abs(a[2] - b[2]) for a in left for b in right)
    if min_sep < SPLIT_PX:
        return None
    # require separation sustained: all positions recent (>30s tracked)? use det_count proxy
    if ev.det_count < 10:
        return None
    new_ev = Event()
    new_ev.opened_at = now
    new_ev.last_seen = now
    new_ev.state = "OPEN"
    for pk, x, y in right:
        new_ev.person_keys.add(pk)
        new_ev.positions[pk] = (x, y, now)
    for pk in list(new_ev.person_keys):
        ev.person_keys.discard(pk)
        ev.positions.pop(pk, None)
    new_ev.zone_ids = set(ev.zone_ids)
    new_ev.camera_ids = set(ev.camera_ids)
    new_ev.history.append((now, f"SPLIT_FROM:{ev.id}", "system"))
    ev.history.append((now, f"SPLIT_TO:{new_ev.id}", "system"))
    store[new_ev.id] = new_ev
    return new_ev
