"""
alarm_manager/src/api.py  (v3 — per-camera streams + cameras API)
Owner: Prince
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os

def _require_fence_key(request: Request) -> JSONResponse | None:
    """Free minimal guard for fence-write. If IBVAP_API_KEY is unset, allow (local dev).
    If set, require header X-API-Key to match. Protects border CCTV calibration from open LAN."""
    expected = os.environ.get("IBVAP_API_KEY", "")
    if not expected:
        return None
    got = request.headers.get("x-api-key", "")
    if got != expected:
        return JSONResponse(status_code=401, content={"error": "invalid or missing X-API-Key"})
    return None

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alarm_manager.src.database import get_recent_events, init_db
from alarm_manager.src.incident_store import get_all_incidents
from alarm_manager.src.frame_buffer import LIVE_FRAME, CAMERA_REGISTRY
from alarm_manager.src import register_subscriber, unregister_subscriber

app = FastAPI(title="SEEMA DRISHTI API v3")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

try:
    from face_recognition.router import router as face_router
    app.include_router(face_router)
except Exception as e:
    import traceback
    print("==================================================")
    print(f"CRITICAL ERROR: Could not import face_recognition router!")
    print("The API endpoints for face recognition will NOT be available.")
    traceback.print_exc()
    print("==================================================")

# Static: snapshots, incidents, website
_STORAGE     = Path(__file__).resolve().parents[2] / "storage"
_WEBSITE_DIR = Path(__file__).resolve().parents[2] / "website" / "dashboard" / "dist"
_INCIDENTS   = _STORAGE / "incidents"

app.mount("/storage", StaticFiles(directory=str(_STORAGE)), name="storage")
if _WEBSITE_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_WEBSITE_DIR), html=True), name="ui")


@app.on_event("startup")
async def _startup(): init_db()


@app.get("/")
async def root():
    return {"status": "SEEMA DRISHTI v3 running", "dashboard": "/ui", "docs": "/docs"}


# ── MJPEG Stream helpers ────────────────────────────────────────────────────
async def _mjpeg_gen(buffer):
    """Yield JPEG frames from any FrameBuffer as multipart."""
    while True:
        frame = buffer.read()
        if frame:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        await asyncio.sleep(0.04)   # ~25 fps max


@app.get("/stream/live")
async def live_stream():
    """Combined grid view of all cameras."""
    return StreamingResponse(
        _mjpeg_gen(CAMERA_REGISTRY.grid),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get('/stream/snapshot/{cam_id}')
async def camera_snapshot(cam_id: str):
    from fastapi import Response
    buf = CAMERA_REGISTRY.get(cam_id)
    if buf is None:
        return JSONResponse(status_code=404, content={'error': f'Camera {cam_id} not found'})
    frame = buf.read()
    if not frame:
        return JSONResponse(status_code=503, content={'error': 'Frame not available'})
    return Response(content=frame, media_type='image/jpeg')

@app.get("/stream/camera/{cam_id}")
async def camera_stream(cam_id: str):
    """Individual camera MJPEG stream."""
    buf = CAMERA_REGISTRY.get(cam_id)
    if buf is None:
        return JSONResponse(status_code=404, content={"error": f"Camera {cam_id} not found"})
    return StreamingResponse(
        _mjpeg_gen(buf),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ── REST APIs ───────────────────────────────────────────────────────────────
@app.get("/api/cameras")
async def api_cameras():
    """List all registered cameras with status."""
    return JSONResponse(content=CAMERA_REGISTRY.get_cameras())


@app.post("/api/cameras/{cam_id}/select")
async def api_select_camera(cam_id: str):
    """Set which camera receives AI processing."""
    CAMERA_REGISTRY.set_ai_cam(cam_id)
    return {"status": "success", "active_ai_cam": CAMERA_REGISTRY.active_ai_cam}


from pydantic import BaseModel
class FenceUpdate(BaseModel):
    polygon: list[list[int]]

@app.get("/api/cameras/{cam_id}/fence")
async def get_camera_fence(cam_id: str):
    nodes = getattr(CAMERA_REGISTRY, '_cam_nodes', [])
    for cam in nodes:
        if cam.id == cam_id:
            # return polygon normalized to current frame dimensions if needed,
            # but usually it's the raw points or the scaled points.
            # VirtualFence scales points in __init__, wait, VirtualFence
            # stores `self.polygon` as scaled points, but the frontend might
            # want points relative to frame size.
            return {"status": "success", "polygon": cam.fence.polygon}
    return JSONResponse(status_code=404, content={"error": f"Camera {cam_id} not running"})

@app.post("/api/cameras/{cam_id}/fence")
async def update_camera_fence(cam_id: str, payload: FenceUpdate, request: Request):
    denied = _require_fence_key(request)
    if denied is not None:
        return denied
    nodes = getattr(CAMERA_REGISTRY, '_cam_nodes', [])
    for cam in nodes:
        if cam.id == cam_id:
            cam.fence.update_polygon(payload.polygon)
            return {"status": "success"}
    return JSONResponse(status_code=404, content={"error": f"Camera {cam_id} not running"})


@app.get("/api/live")
async def api_live():
    """Per-frame live telemetry from the camera pipeline."""
    return JSONResponse(content=CAMERA_REGISTRY.get_live_info())


@app.get("/api/stats")
async def api_stats():
    """Aggregate stats for the dashboard stat cards."""
    from alarm_manager.src.database import get_stats
    stats = get_stats()
    incidents_list = get_all_incidents(10000) # just get a rough count or modify get_all_incidents to count
    stats["incidents"] = {"value": len(incidents_list), "label": "Total Incidents"}
    return stats


@app.get("/api/events")
async def api_events(limit: int = 50):
    return JSONResponse(content=get_recent_events(limit))


# ── Mission Control event layer (MC-4) ────────────────────────────────────
@app.get("/api/zones")
async def api_zones():
    """Static schematic layout + live zone state. Offline-first (no map tiles).

    Position is a 1000x600 viewBox slot derived deterministically from cam
    index so frontend needs zero config. When CAMERA_REGISTRY has live cams,
    they are returned; else a 3-zone demo skeleton is returned for UI dev.
    """
    cams = []
    try:
        cams = CAMERA_REGISTRY.get_cameras() or []
    except Exception:
        cams = []
    zones = []
    if cams:
        for i, c in enumerate(cams):
            cid = c.get("id", f"CAM_{i+1:02d}")
            zones.append({
                "zone_id": f"{cid}-perimeter",
                "camera_id": cid,
                "name": c.get("name", cid),
                "x": 120 + (i % 4) * 220,
                "y": 140 + (i // 4) * 180,
                "status": "nominal",
                "armed": True,
            })
    else:
        zones = [
            {"zone_id": "north-fence", "camera_id": "CAM_01", "name": "North Fence", "x": 150, "y": 150, "status": "nominal", "armed": True},
            {"zone_id": "gate-road", "camera_id": "CAM_02", "name": "Gate Road", "x": 420, "y": 220, "status": "nominal", "armed": True},
            {"zone_id": "south-road", "camera_id": "CAM_03", "name": "South Road", "x": 690, "y": 150, "status": "nominal", "armed": True},
        ]
    # overlay live open-event states
    try:
        from alarm_manager.src.database import get_open_events
        for ev in get_open_events(50):
            import json as _j
            for zid in (_j.loads(ev.get("zone_ids") or "[]") if isinstance(ev.get("zone_ids"), str) else (ev.get("zone_ids") or [])):
                for z in zones:
                    if z["zone_id"] == zid or z["camera_id"] in str(zid):
                        z["status"] = "intrusion" if ev.get("state") in ("ESCALATING", "DISPATCHED") else "activity"
    except Exception:
        pass
    return {"zones": zones, "viewBox": "0 0 1000 600"}


class EventTransition(BaseModel):
    to_state: str
    actor: str = "operator"
    reason: str = ""


@app.post("/api/events/{event_id}/transition")
async def api_event_transition(event_id: str, payload: EventTransition, request: Request):
    """ACK / DISPATCH / RESOLVE / FALSE_ALARM with audit log. Fence-key guard reused."""
    denied = _require_fence_key(request)
    # writes require key only when IBVAP_API_KEY is set (local dev stays open)
    if denied is not None:
        return denied
    try:
        from alarm_manager.src.database import transition_event
        return transition_event(event_id, payload.to_state, payload.actor, payload.reason)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/open-events")
async def api_open_events(limit: int = 50):
    from alarm_manager.src.database import get_open_events
    return JSONResponse(content=get_open_events(limit))


@app.get("/api/incidents")
async def api_incidents(limit: int = 30):
    return JSONResponse(content=get_all_incidents(limit))


@app.get("/api/incidents/{incident_id}")
async def api_incident_detail(incident_id: str):
    meta_file = _INCIDENTS / incident_id / "incident.json"
    if not meta_file.exists():
        return JSONResponse(status_code=404, content={"error": "not found"})
    import json
    return JSONResponse(content=json.loads(meta_file.read_text()))


@app.get("/api/ledger/verify/{incident_id}")
async def api_ledger_verify(incident_id: str):
    """Free offline tamper check: recompute structural validity + return hashes for
    client-side re-walk. Full chain re-walk uses incident.json ledger link."""
    import json as _json
    # incidents are stored as storage/incidents/<camera>/<incident>/incident.json
    matches = list(_INCIDENTS.rglob(f"{incident_id}/incident.json"))
    if not matches:
        # legacy flat layout fallback
        legacy = _INCIDENTS / incident_id / "incident.json"
        if legacy.exists():
            matches = [legacy]
    if not matches:
        return JSONResponse(status_code=404, content={"error": "incident not found"})
    try:
        meta = _json.loads(matches[0].read_text())
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"read failed: {e}"})
    try:
        from alarm_manager.src.ledger import verify_incident_chain, build_anchor_payload
        v = verify_incident_chain(meta)
        anchor = build_anchor_payload([incident_id], [((meta.get("ledger") or {}).get("curr_hash") or "")])
        return {"incident_id": incident_id, "verification": v, "anchor_preview": anchor,
                "note": "offline valid=True means hash present+well-formed. Anchor merkle_root when online via OpenTimestamps/Polygon Amoy (free testnet)."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── WebSocket live alerts ───────────────────────────────────────────────────
@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    register_subscriber(q)
    try:
        while True:
            alert = await q.get()
            await websocket.send_json(alert)
    except WebSocketDisconnect:
        pass
    finally:
        unregister_subscriber(q)
