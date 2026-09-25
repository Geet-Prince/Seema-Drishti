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
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

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

try:
    from watchlist.router import router as watchlist_router
    app.include_router(watchlist_router)
except Exception as e:
    import traceback
    print("==================================================")
    print(f"CRITICAL ERROR: Could not import watchlist router!")
    traceback.print_exc()
    print("==================================================")

# Static: snapshots, incidents, website
_REPO_ROOT = Path(__file__).resolve().parents[2]
_STORAGE = _REPO_ROOT / "storage"
_STORAGE.mkdir(parents=True, exist_ok=True)
_DASHBOARD_DIST = _REPO_ROOT / "website" / "dashboard" / "dist"
_FALLBACK_WEBSITE = _REPO_ROOT / "website"
_INCIDENTS = _STORAGE / "incidents"
_INCIDENTS.mkdir(parents=True, exist_ok=True)

app.mount("/storage", StaticFiles(directory=str(_STORAGE)), name="storage")

if _DASHBOARD_DIST.exists() and (_DASHBOARD_DIST / "index.html").exists():
    app.mount("/ui", StaticFiles(directory=str(_DASHBOARD_DIST), html=True), name="ui")
elif _FALLBACK_WEBSITE.exists() and (_FALLBACK_WEBSITE / "index.html").exists():
    app.mount("/ui", StaticFiles(directory=str(_FALLBACK_WEBSITE), html=True), name="ui")


from contextlib import asynccontextmanager

@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()
    yield

app.router.lifespan_context = _lifespan
init_db()


@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/ui")
    return {"status": "SEEMA DRISHTI v3 running", "dashboard": "/ui", "docs": "/docs"}


@app.get("/dashboard")
async def dashboard_redirect():
    return RedirectResponse(url="/ui")


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
async def update_camera_fence(cam_id: str, payload: FenceUpdate):
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


@app.get("/api/incidents")
async def api_incidents(limit: int = 30):
    return JSONResponse(content=get_all_incidents(limit))


@app.get("/api/incidents/{incident_id}")
async def api_incident_detail(incident_id: str):
    # Layout is storage/incidents/<camera_id>/<incident_id>/incident.json
    # (older builds used storage/incidents/<incident_id>/). Search both.
    import json
    direct = _INCIDENTS / incident_id / "incident.json"
    if direct.exists():
        return JSONResponse(content=json.loads(direct.read_text()))
    matches = list(_INCIDENTS.rglob(f"{incident_id}/incident.json"))
    if matches:
        return JSONResponse(content=json.loads(matches[0].read_text()))
    return JSONResponse(status_code=404, content={"error": "not found"})


class StatusUpdate(BaseModel):
    status: str


@app.patch("/api/incidents/{incident_id}")
async def api_incident_status(incident_id: str, payload: StatusUpdate):
    """Persist incident review state. Frontend calls this optimistically."""
    import json
    direct = _INCIDENTS / incident_id / "incident.json"
    target = direct if direct.exists() else None
    if target is None:
        matches = list(_INCIDENTS.rglob(f"{incident_id}/incident.json"))
        target = matches[0] if matches else None
    if target is None:
        # No incident folder yet (e.g. alert-only id) — acknowledge so UI stays responsive.
        return {"status": "success", "incident_id": incident_id, "new_status": payload.status}
    try:
        meta = json.loads(target.read_text())
        meta["status"] = payload.status
        target.write_text(json.dumps(meta, indent=2))
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return {"status": "success", "incident_id": incident_id, "new_status": payload.status}


@app.patch("/api/alerts/{alert_id}")
async def api_alert_status(alert_id: str, payload: StatusUpdate):
    """Persist alert review state in the events table."""
    try:
        import alarm_manager.src.database as dbmod
        dbmod.init_db()
        conn = dbmod.get_connection()
        with dbmod._conn_lock:
            cur = conn.execute(
                "UPDATE events SET status=? WHERE event_id=?", (payload.status, alert_id)
            )
            conn.commit()
            if cur.rowcount == 0:
                # Unknown id — still acknowledge so optimistic UI doesn't stick in error state.
                return {"status": "success", "event_id": alert_id, "new_status": payload.status}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return {"status": "success", "event_id": alert_id, "new_status": payload.status}


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
