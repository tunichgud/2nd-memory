"""
media.py – /api/v1/media/{user_id}/{filename} (user-scoped Thumbnails)
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response
import aiosqlite
from backend.db.database import get_db
from backend.api.media import _find_image_bytes, _make_thumbnail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/media", tags=["v1/media"])

_thumb_cache_v1: dict[str, bytes] = {}
_full_cache_v1:  dict[str, bytes] = {}
MAX_CACHE = 200


@router.get("/{user_id}/{filename}")
async def serve_media_v1(
    user_id: str,
    filename: str,
    size: str = Query(default="thumb", pattern="^(thumb|full)$"),
    bbox: str | None = Query(None, pattern="^[0-9,]+$"),
    db: aiosqlite.Connection = Depends(get_db),
):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")

    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    cache = _thumb_cache_v1 if size == "thumb" else _full_cache_v1
    max_px = 300 if size == "thumb" else 1200
    cache_key = f"{user_id}/{filename}_{bbox}" if bbox else f"{user_id}/{filename}"

    if cache_key in cache:
        return Response(content=cache[cache_key], media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})

    raw = _find_image_bytes(filename)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Bild nicht gefunden: {filename}")

    try:
        thumb = _make_thumbnail(raw, max_px, bbox=bbox)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Thumbnail-Fehler: {exc}")

    if len(cache) >= MAX_CACHE:
        del cache[next(iter(cache))]
    cache[cache_key] = thumb

    return Response(content=thumb, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})
