import os
import cv2
import numpy as np
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from alarm_manager.src.database import (
    insert_known_personnel,
    get_all_known_personnel,
    delete_known_personnel,
)
from .core import FaceRecognitionWorker, get_pipeline_worker

router = APIRouter()

# Lazy-init a fallback worker for embedding extraction at upload time.
# The live PIPELINE worker (registered via set_pipeline_worker in run_ibvap.py)
# is used for FAISS reloads so uploads are immediately reflected in the feed.
_api_worker: FaceRecognitionWorker | None = None


def _get_api_worker() -> FaceRecognitionWorker:
    """Return the API-local worker, creating it on first use."""
    global _api_worker
    if _api_worker is None:
        _api_worker = FaceRecognitionWorker()
    return _api_worker


def _reload_all() -> None:
    """Reload FAISS index on every available worker after a DB change."""
    # Prefer the live pipeline worker (same process as video loop)
    pw = get_pipeline_worker()
    if pw is not None:
        try:
            pw.reload_database()
        except Exception as exc:
            print(f"[FACE] pipeline worker reload error: {exc}")
    # Always reload the API worker too (used for extract_embedding)
    if _api_worker is not None:
        try:
            _api_worker.reload_database()
        except Exception as exc:
            print(f"[FACE] API worker reload error: {exc}")


# Uploads are stored inside ibvap/storage/known_faces/ which is served at /storage
STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage" / "known_faces"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/api/personnel")
async def add_personnel(
    name: str = Form(...),
    badge_number: str = Form(""),
    file: UploadFile = File(...),
):
    """Register a new known-personnel face: extracts embedding, saves image, writes to DB."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Invalid image format.")

    embedding = _get_api_worker().extract_embedding(img_bgr)
    if embedding is None:
        raise HTTPException(
            status_code=400,
            detail="No face detected in the uploaded image. Please use a clear front-facing photo.",
        )

    # Save image to ibvap/storage/known_faces/ (served as /storage/known_faces/…)
    safe_name = name.replace(" ", "_")
    filename = f"{safe_name}_{badge_number}.jpg" if badge_number else f"{safe_name}.jpg"
    image_path = STORAGE_DIR / filename
    cv2.imwrite(str(image_path), img_bgr)

    web_path = f"/storage/known_faces/{filename}"
    insert_known_personnel(name, badge_number, web_path, embedding.tolist())

    # Hot-reload the live pipeline — new face is recognised immediately
    _reload_all()

    return JSONResponse({"status": "success", "message": f"{name} registered successfully."})


@router.get("/api/personnel")
async def list_personnel():
    """Return all registered personnel (embeddings excluded)."""
    personnel = get_all_known_personnel()
    for p in personnel:
        p.pop("embedding", None)
    return JSONResponse({"status": "success", "data": personnel})


@router.delete("/api/personnel/{person_id}")
async def remove_personnel(person_id: int):
    """Delete a personnel record and hot-reload the pipeline index."""
    deleted = delete_known_personnel(person_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Personnel id {person_id} not found.")

    # Hot-reload — deleted face is no longer matched immediately
    _reload_all()

    return JSONResponse({"status": "success", "message": f"Personnel {person_id} removed."})
