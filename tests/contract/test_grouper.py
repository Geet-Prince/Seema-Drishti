"""Contract tests for Intrusion Event grouper (MC-1/MC-3). No GPU, synthetic only."""
import shutil
from datetime import datetime, timezone
from pathlib import Path

from alarm_manager.src import grouper
from alarm_manager.src.grouper import Event


def test_grouping_same_zone_time_is_one_event():
    store = {}
    e1, c1 = grouper.ingest_detection(store, "CAM_01", "h-1", "north-fence", "loitering", 40, (100, 100), now=1000.0)
    e2, c2 = grouper.ingest_detection(store, "CAM_01", "h-2", "north-fence", "loitering", 40, (120, 105), now=1010.0)
    assert c1 is True and c2 is False
    assert e1.id == e2.id
    assert e1.headcount == 2


def test_time_gap_opens_new_event():
    store = {}
    e1, _ = grouper.ingest_detection(store, "CAM_01", "h-1", "north-fence", None, 20, (100, 100), now=1000.0)
    e2, created = grouper.ingest_detection(store, "CAM_01", "h-9", "north-fence", None, 20, (100, 100), now=1200.0)
    assert created is True
    assert e1.id != e2.id


def test_reid_dedup_across_cams():
    store = {}
    e1, _ = grouper.ingest_detection(store, "CAM_01", "h-1", "north-fence", None, 40, (100, 100),
                                     attributes={"reid_cluster": "P-AAA"}, now=1000.0)
    e2, created = grouper.ingest_detection(store, "CAM_02", "h-7", "gate-road", None, 40, (500, 300),
                                           attributes={"reid_cluster": "P-AAA"}, now=1050.0)
    assert created is False  # same person handed off, not double-counted
    assert e1.id == e2.id
    assert e1.headcount == 1
    assert {"CAM_01", "CAM_02"} <= e1.camera_ids


def test_merge_adjacent_shared_behaviour():
    store = {}
    grouper.ADJACENCY["north-fence"] = ["gate-road"]
    try:
        e1, _ = grouper.ingest_detection(store, "CAM_01", "h-1", "north-fence", "loitering", 40, (100, 100), now=1000.0)
        e2, _ = grouper.ingest_detection(store, "CAM_02", "h-2", "gate-road", "loitering", 40, (110, 110), now=1010.0)
        # ingest may already link via adjacency+behaviour (score 40 <50) so 2 events; force merge check
        if e1.id != e2.id:
            merged = grouper.check_merge(store, e2, now=1020.0)
            assert merged is not None
            assert store[merged.id].headcount == 2
    finally:
        grouper.ADJACENCY.pop("north-fence", None)


def test_split_far_clusters():
    store = {}
    ev = Event()
    ev.det_count = 20
    ev.zone_ids.add("north-fence")
    ev.person_keys.update({"P-1", "P-2"})
    ev.positions = {"P-1": (50, 50, 1000.0), "P-2": (600, 400, 1000.0)}
    store[ev.id] = ev
    new_ev = grouper.check_split(store, ev, now=1030.0)
    assert new_ev is not None
    assert new_ev.id != ev.id
    assert len(store) == 2


def test_lifecycle_escalate_and_close():
    store = {}
    e1, _ = grouper.ingest_detection(store, "CAM_01", "h-1", "north-fence", "loitering", 70, (100, 100), now=1000.0)
    updates = grouper.sweep(store, now=1001.0)
    assert store[e1.id].state == "ESCALATING"
    updates2 = grouper.sweep(store, now=1000.0 + grouper.DORMANT_CLOSE + 10)
    assert store[e1.id].state == "RESOLVED"
    assert len(updates) >= 1 and len(updates2) >= 1


def test_alarm_wiring_continuous_session_groups_two_tracks():
    """MC-7: two fence-breach vehicles in one window => ONE event_id, headcount 2,
    dossier keeps appending (incident folders for both tracks)."""
    from alarm_manager.src.core import AlarmManager
    from contracts.schema import DetectionResult, DetectedObject

    am = AlarmManager()
    incident_ids = []
    try:
        for tid in ("veh-1", "veh-2"):
            obj = DetectedObject(object_type="vehicle", track_id=tid,
                                 bbox=(10, 10, 100, 100), confidence=0.8,
                                 attributes={"zone_state": "inside", "zone_id": "north-fence",
                                             "vehicle_type": "car", "centroid": (55, 55)})
            res = DetectionResult(module="human_tracking", camera_id="CAM_T",
                                  frame_id=1, timestamp_utc=datetime.now(timezone.utc),
                                  objects=[obj])
            am.submit(res, frame=None)
            assert "event_id" in obj.attributes, "wiring must attach event_id"
            incident_ids.append(obj.attributes["event_id"])
        assert incident_ids[0] == incident_ids[1], f"expected one session, got {incident_ids}"
        ev = am._event_store[incident_ids[0]]
        assert ev.headcount == 2
    finally:
        # cleanup: incident folders + intrusion_events rows + events rows
        import hashlib
        from alarm_manager.src.database import get_connection
        for tid in ("veh-1", "veh-2"):
            iid = hashlib.md5(f"CAM_T-{tid}".encode()).hexdigest()[:12]
            shutil.rmtree(Path("storage") / "incidents" / "CAM_T" / iid, ignore_errors=True)
            shutil.rmtree(Path("storage/incidents").resolve() / "CAM_T" / iid, ignore_errors=True)
        try:
            conn = get_connection()
            conn.execute("DELETE FROM intrusion_events WHERE event_id=?", (incident_ids[0],))
            for tid in ("veh-1", "veh-2"):
                iid = hashlib.md5(f"CAM_T-{tid}".encode()).hexdigest()[:12]
                conn.execute("DELETE FROM events WHERE event_id=?", (iid,))
            conn.commit()
        except Exception:
            pass
