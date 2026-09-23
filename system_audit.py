"""
IBVAP System Audit Script
Checks every module can be imported and the full pipeline handshake works.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results = []

def check(name, fn):
    try:
        fn()
        results.append((PASS, name))
    except Exception as e:
        results.append((FAIL, f"{name}  ->  {e}"))

# ─── 1. Contracts ───────────────────────────────────────────────────────────
def _contracts():
    from contracts.schema import DetectionResult, DetectedObject
    obj = DetectedObject(object_type="human", track_id="h-1",
                         bbox=[10.0,10.0,100.0,200.0], confidence=0.95, attributes={})
    r = DetectionResult(module="human_tracking", camera_id="CAM_LIVE",
                        frame_id=1, timestamp_utc=__import__('datetime').datetime.utcnow(), objects=[obj])
    assert r.module == "human_tracking"
check("Contracts schema (DetectionResult + DetectedObject)", _contracts)

# ─── 2. Alarm Manager DB ────────────────────────────────────────────────────
def _db():
    from alarm_manager.src.database import init_db
    init_db()
check("Alarm Manager — SQLite DB init", _db)

# ─── 3. Alarm Manager Rules ─────────────────────────────────────────────────
def _rules():
    from alarm_manager.src.core import AlarmManager
    am = AlarmManager()
    assert len(am._rules) > 0, "No rules loaded!"
    print(f"   Rules loaded: {[r['name'] for r in am._rules]}")
check("Alarm Manager — rules.yaml loaded", _rules)

# ─── 4. Scoring — Human Tracked ─────────────────────────────────────────────
def _score_human():
    from alarm_manager.src.core import AlarmManager
    am = AlarmManager()
    score, rule = am._score("human_tracking", {}, object_type="human")
    assert score == 20, f"Expected 20, got {score}"
check("Scoring — human_tracking gets score=20", _score_human)

# ─── 5. Scoring — Fence Breach ──────────────────────────────────────────────
def _score_fence():
    from alarm_manager.src.core import AlarmManager
    am = AlarmManager()
    score, rule = am._score("human_tracking", {"zone_state": "inside", "zone_id": "border_fence"}, object_type="human")
    assert score == 40, f"Expected 40, got {score}"
check("Scoring — fence breach gets score=40", _score_fence)

# ─── 6. Scoring — Loitering ─────────────────────────────────────────────────
def _score_loiter():
    from alarm_manager.src.core import AlarmManager
    am = AlarmManager()
    score, rule = am._score("human_tracking", {"activity": "loitering"})
    assert score == 35, f"Expected 35, got {score}"
check("Scoring — loitering gets score=35", _score_loiter)

# ─── 7. Scoring — Vehicle ───────────────────────────────────────────────────
def _score_vehicle():
    from alarm_manager.src.core import AlarmManager
    am = AlarmManager()
    score, rule = am._score("vehicle_detection", {"vehicle_type": "car"})
    assert score == 25, f"Expected 25, got {score}"
check("Scoring — vehicle_detection gets score=25", _score_vehicle)

# ─── 8. Incident Store ──────────────────────────────────────────────────────
def _incident_store():
    from alarm_manager.src.incident_store import load_or_create, save, get_all_incidents
    meta = load_or_create("test-audit-001", "CAM_TEST", "human_tracking", 20, "LOW")
    assert meta["incident_id"] == "test-audit-001"
    assert "humans_detected" in meta
    assert "vehicle_types" in meta
    assert "faces_captured" in meta
    assert "activities_detected" in meta
    assert "zone_breaches" in meta
    assert "plate_numbers" in meta
check("Incident Store — all metadata fields present", _incident_store)

# ─── 9. Suspicious Activity Module ──────────────────────────────────────────
def _suspicious():
    from suspicious_activity.loitering_detector import SuspiciousActivityDetector
    from contracts.schema import DetectionResult, DetectedObject
    import datetime
    obj = DetectedObject(object_type="human", track_id="h-1",
                         bbox=[10.0,10.0,100.0,200.0], confidence=0.9,
                         attributes={"centroid": (55, 105), "velocity_px_per_s": (0.0, 0.0)})
    r = DetectionResult(module="human_tracking", camera_id="CAM_LIVE",
                        frame_id=1, timestamp_utc=datetime.datetime.utcnow(), objects=[obj])
    detector = SuspiciousActivityDetector()
    result = detector.process(r)
    assert result is not None
    assert result.objects[0].track_id == "h-1"
check("Suspicious Activity — process() returns valid DetectionResult", _suspicious)

# ─── 10. Virtual Fence Module ───────────────────────────────────────────────
def _fence():
    from virtual_fence.fence_detector import VirtualFence
    from contracts.schema import DetectionResult, DetectedObject
    import datetime
    fence = VirtualFence(frame_w=1280, frame_h=720)
    obj = DetectedObject(object_type="human", track_id="h-1",
                         bbox=[400.0, 400.0, 500.0, 600.0], confidence=0.9, attributes={})
    r = DetectionResult(module="human_tracking", camera_id="CAM_LIVE",
                        frame_id=1, timestamp_utc=datetime.datetime.utcnow(), objects=[obj])
    result = fence.process(r)
    assert result is not None
    inside = result.objects[0].attributes.get("zone_state")
    print(f"   Fence result: zone_state={inside} (expected 'inside' or None depending on polygon)")
check("Virtual Fence — process() returns valid DetectionResult", _fence)

# ─── 11. Vehicle ANPR Module ────────────────────────────────────────────────
def _vehicle():
    from vehicle_detection.inference.vehicle_anpr import VehicleANPR
    # Only check it can be imported and instantiated (model loading)
    # Don't run actual detection as it needs a frame
    v = VehicleANPR.__new__(VehicleANPR)  # bypass __init__ for audit
    assert hasattr(v, 'process')
check("Vehicle ANPR — module importable and has process()", _vehicle)

# ─── 12. API endpoints ──────────────────────────────────────────────────────
def _api():
    from alarm_manager.src.api import app
    routes = [getattr(r, "path", "") for r in app.routes if hasattr(r, "path")]
    assert "/stream/live" in routes
    assert "/api/events" in routes
    assert "/api/incidents" in routes
    assert "/ws/alerts" in routes
    # optimization branch routes (ledger verify) — warn, don't fail legacy
    assert "/api/ledger/verify/{incident_id}" in routes, "ledger verify route missing"
check("FastAPI — all critical routes registered", _api)

# ─── 13. Frame Buffer ───────────────────────────────────────────────────────
def _frame_buffer():
    import numpy as np
    from alarm_manager.src.frame_buffer import LIVE_FRAME
    dummy = np.zeros((100, 100, 3), dtype=np.uint8)
    LIVE_FRAME.write(dummy)
    import time
    time.sleep(0.05)
    data = LIVE_FRAME.read()
    assert data is not None and len(data) > 0
check("Frame Buffer — thread-safe read/write works", _frame_buffer)

# ─── 14. Cumulative scoring (optimization branch) ─────────────────────────
def _score_total():
    from alarm_manager.src.core import AlarmManager
    am = AlarmManager()
    total, best, matched = am._score_total(
        "human_tracking", {"zone_state": "inside", "activity": "loitering"},
        object_type="human")
    # Human Tracked 20 + Fence 40 + Loitering 35 = 95 (docs math must hold)
    assert total == 95, f"Expected cumulative 95, got {total} matched={[r['name'] for r in matched]}"
    assert best is not None
check("Scoring TOTAL — human+fence+loitering sums to 95", _score_total)

# ─── 15. Hash-chain ledger (optimization branch) ──────────────────────────
def _ledger():
    from alarm_manager.src.ledger import chain_hash, next_entry, merkle_root
    h1 = chain_hash("GENESIS", "abc123", 95, "2026-09-21T00:00:00+00:00", "snapshot_001.jpg", {"a": 1})
    h2 = chain_hash("GENESIS", "abc123", 95, "2026-09-21T00:00:00+00:00", "snapshot_001.jpg", {"a": 1})
    assert h1 == h2 and len(h1) == 64, "ledger hash must be deterministic sha256"
    e = next_entry("GENESIS", "abc123", 95, "2026-09-21T00:00:00+00:00")
    assert e["prev_hash"] == "GENESIS" and len(e["curr_hash"]) == 64
    assert merkle_root([h1, h2]) != ""
check("Ledger — hash-chain deterministic + merkle root works", _ledger)

# ─── 16. Mission Control event tables (MC-2) ───────────────────────────────
def _event_tables():
    from alarm_manager.src.database import init_db, upsert_intrusion_event, transition_event, get_open_events
    init_db()
    upsert_intrusion_event({"event_id": "ESC-AUDIT", "state": "OPEN", "zones": ["north-fence"],
                            "cameras": ["CAM_01"], "person_keys": ["P-1"], "track_ids": ["CAM_01:h-1"],
                            "behaviours": ["loitering"], "headcount": 1, "score_max": 55,
                            "det_count": 3, "opened_at": "2026-09-21T00:00:00+00:00",
                            "last_seen": "2026-09-21T00:01:00+00:00"})
    r = transition_event("ESC-AUDIT", "ACKED", actor="audit", reason="check")
    assert r["to"] == "ACKED", f"transition failed: {r}"
    opens = get_open_events(10)
    assert any(o["event_id"] == "ESC-AUDIT" for o in opens)
check("Mission Control — intrusion_events + transition ACKED works", _event_tables)

# ─── 17. Mission Control API routes (MC-4) ────────────────────────────────
def _mc_routes():
    from alarm_manager.src.api import app
    routes = [getattr(r, "path", "") for r in app.routes if hasattr(r, "path")]
    assert "/api/zones" in routes, "missing /api/zones"
    assert "/api/open-events" in routes, "missing /api/open-events"
check("Mission Control — /api/zones + /api/open-events registered", _mc_routes)

# ─── Print Report ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  IBVAP FULL SYSTEM AUDIT REPORT")
print("=" * 60)
for status, name in results:
    print(f"  [{status}]  {name}")

passed = sum(1 for s, _ in results if s == PASS)
failed = sum(1 for s, _ in results if s == FAIL)
print(f"\n  Total: {passed} passed, {failed} failed out of {len(results)} checks")
print("=" * 60)
if failed == 0:
    print("  🎉 ALL SYSTEMS OPERATIONAL — Ready to run!")
else:
    print("  ⚠️  Fix the above failures before running the pipeline.")
