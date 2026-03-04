"""
map.py – /api/v1/locations (user-scoped GPS-Punkte)
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite
from backend.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["v1/map"])


class LocationPoint(BaseModel):
    id: str
    source: str
    name: str
    lat: float
    lon: float
    date_iso: str
    extra: dict


@router.get("/locations")
async def get_locations_v1(
    user_id: str,
    source: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """GPS-Punkte für Kartenansicht, gefiltert nach user_id."""
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    from backend.rag.store_v2 import get_all_documents_for_user, COLLECTIONS
    from datetime import datetime

    points = []
    target_cols = [source] if source else [c for c in COLLECTIONS if c != "messages"]

    for col_name in target_cols:
        data = get_all_documents_for_user(col_name, user_id)
        if not data["ids"]:
            continue
        for doc_id, meta in zip(data["ids"], data["metadatas"]):
            lat = meta.get("lat", 0.0)
            lon = meta.get("lon", 0.0)
            if not lat and not lon:
                continue
            if lat == 0.0 and lon == 0.0:
                continue
            if date_from or date_to:
                ts = meta.get("date_ts", 0)
                if date_from:
                    try:
                        if ts < int(datetime.fromisoformat(date_from).timestamp()):
                            continue
                    except ValueError:
                        pass
                if date_to:
                    try:
                        if ts > int(datetime.fromisoformat(date_to).timestamp()):
                            continue
                    except ValueError:
                        pass
            name = meta.get("name") or meta.get("filename") or doc_id
            extra = {}
            if col_name == "photos":
                extra = {"persons": meta.get("persons", ""), "cluster": meta.get("cluster", "")}
            elif col_name in ("reviews", "saved_places"):
                extra = {
                    "address": meta.get("address", ""),
                    "rating": meta.get("rating", 0),
                    "maps_url": meta.get("maps_url", ""),
                }
            points.append(LocationPoint(
                id=doc_id, source=col_name, name=name,
                lat=lat, lon=lon, date_iso=meta.get("date_iso", ""), extra=extra,
            ))

    return {"points": [p.model_dump() for p in points], "total": len(points)}
