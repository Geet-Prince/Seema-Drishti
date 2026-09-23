"""Number-plate watchlist API — register plates to get instant alerts + PDF evidence."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from alarm_manager.src.database import (
    add_watchlist_plate,
    get_watchlist_plates,
    normalize_plate,
    remove_watchlist_plate,
)

router = APIRouter()


class WatchlistAdd(BaseModel):
    plate: str
    owner: str = ""
    notes: str = ""


@router.get("/api/watchlist")
async def list_watchlist():
    return JSONResponse({"status": "success", "data": get_watchlist_plates()})


@router.post("/api/watchlist")
async def add_watchlist(payload: WatchlistAdd):
    norm = normalize_plate(payload.plate)
    if len(norm) < 4:
        raise HTTPException(status_code=400, detail="Plate number too short (min 4 characters).")
    try:
        row = add_watchlist_plate(norm, payload.owner, payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"status": "success", "data": row})


@router.delete("/api/watchlist/{plate}")
async def delete_watchlist(plate: str):
    ok = remove_watchlist_plate(plate)
    if not ok:
        raise HTTPException(status_code=404, detail="Plate not on watchlist.")
    return JSONResponse({"status": "success"})
