"""
media.py – FastAPI Medien-Endpunkt für memosaur.

Endpunkte:
  GET /api/media/{filename}           – Originalbild aus ZIP/Ordner (gecacht als Thumbnail)
  GET /api/media/{filename}?size=thumb – 300px Thumbnail (Standard)
  GET /api/media/{filename}?size=full  – Vollbild (max 1920px)
"""

from __future__ import annotations

import io
import logging
import zipfile
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media", tags=["media"])

BASE_DIR = Path(__file__).resolve().parents[2]

# Einfacher In-Memory Cache für Thumbnails (Filename → JPEG-Bytes)
_thumb_cache: dict[str, bytes] = {}
_full_cache:  dict[str, bytes] = {}

MAX_CACHE_ENTRIES = 200  # ca. 200 * 30KB = ~6MB


def _find_image_bytes(filename: str) -> bytes | None:
    """Sucht ein Bild im extrahierten Ordner oder in den ZIPs."""
    import yaml
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 1. Extrahierter Ordner
    photos_dir = BASE_DIR / cfg["paths"]["photos_dir"]
    photo_path = photos_dir / filename
    if photo_path.exists():
        return photo_path.read_bytes()

    # 2. ZIPs durchsuchen
    takeout_root = BASE_DIR / "takeout"
    for zip_path in sorted(takeout_root.glob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as zf:
                matches = [e for e in zf.namelist() if Path(e).name == filename]
                if matches:
                    return zf.read(matches[0])
        except Exception as exc:
            logger.debug("ZIP-Fehler %s: %s", zip_path.name, exc)
            continue

    return None


def _make_thumbnail(image_bytes: bytes, max_px: int) -> bytes:
    """Erstellt ein JPEG-Thumbnail mit max. max_px auf der längsten Seite."""
    from PIL import Image, ImageOps
    import io as _io

    img = Image.open(_io.BytesIO(image_bytes))
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    w, h = img.size
    if max(w, h) > max_px:
        ratio = max_px / max(w, h)
        resample = getattr(Image.Resampling, "LANCZOS", 1)
        img = img.resize((int(w * ratio), int(h * ratio)), resample)

    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = _io.BytesIO()
    quality = 82 if max_px <= 300 else 88
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


@router.get("/{filename}")
async def serve_media(
    filename: str,
    size: str = Query(default="thumb", pattern="^(thumb|full)$"),
) -> Response:
    """Liefert ein Bild als JPEG aus.

    - size=thumb (Standard): max. 300px, für Quellen-Vorschau
    - size=full: max. 1200px, für Lightbox-Ansicht
    """
    # Sicherheitscheck: kein Pfad-Traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")

    cache = _thumb_cache if size == "thumb" else _full_cache
    max_px = 300 if size == "thumb" else 1200

    # Cache-Hit
    if filename in cache:
        return Response(content=cache[filename], media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})

    # Bild laden
    raw = _find_image_bytes(filename)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Bild nicht gefunden: {filename}")

    # Thumbnail erstellen
    try:
        thumb = _make_thumbnail(raw, max_px)
    except Exception as exc:
        logger.error("Thumbnail-Fehler für %s: %s", filename, exc)
        raise HTTPException(status_code=500, detail="Thumbnail-Fehler")

    # Cachen (LRU-ähnlich: älteste Einträge entfernen wenn voll)
    if len(cache) >= MAX_CACHE_ENTRIES:
        oldest = next(iter(cache))
        del cache[oldest]
    cache[filename] = thumb

    return Response(
        content=thumb,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
