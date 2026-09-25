import os
import cv2
import numpy as np
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from alarm_manager.src.database import insert_known_personnel, get_all_known_personnel
from .core import FaceRecognitionWorker

router = APIRouter()

# We will initialize this lazily when an upload actually happens
# to prevent double-loading the ONNX models at startup which causes deadlocks.
_api_worker = None

def get_api_worker():
    global _api_worker
    if _api_worker is None:
        _api_worker = FaceRecognitionWorker()
    return _api_worker

STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage" / "known_faces"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Legacy location from older builds (faces were saved under
# <projects>/storage/known_faces instead of <ibvap>/storage/known_faces,
# which the API actually serves at /storage). Migrate any stragglers once
# so previously uploaded faces keep working.
_LEGACY_DIR = Path(__file__).resolve().parents[2] / "storage" / "known_faces"

def _migrate_legacy_faces() -> None:
    try:
        if _LEGACY_DIR.exists():
            for f in _LEGACY_DIR.iterdir():
                if f.is_file():
                    dest = STORAGE_DIR / f.name
                    if not dest.exists():
                        try:
                            import shutil
                            shutil.copy2(str(f), str(dest))
                        except Exception:
                            pass
    except Exception:
        pass

_migrate_legacy_faces()

@router.post("/api/personnel")
async def add_personnel(
    name: str = Form(...),
    badge_number: str = Form(""),
    file: UploadFile = File(...)
):
    """Register a new known personnel face."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Invalid image format.")
        
    embedding = get_api_worker().extract_embedding(img_bgr)
    if embedding is None:
        raise HTTPException(status_code=400, detail="No face detected in the image.")
        
    # Save image locally
    filename = f"{name.replace(' ', '_')}_{badge_number}.jpg"
    image_path = str(STORAGE_DIR / filename)
    cv2.imwrite(image_path, img_bgr)
    
    # Save to DB
    insert_known_personnel(name, badge_number, f"/storage/known_faces/{filename}", embedding.tolist())
    
    # Ask any running workers to reload their DB (Optional if sharing memory, but we can't easily cross processes)
    get_api_worker().reload_database()
    
    return JSONResponse({"status": "success", "message": f"{name} registered successfully."})

@router.get("/api/personnel")
async def list_personnel():
    """Get all registered personnel."""
    personnel = get_all_known_personnel()
    # Don't send embeddings to the frontend
    for p in personnel:
        p.pop('embedding', None)
    return JSONResponse({"status": "success", "data": personnel})
