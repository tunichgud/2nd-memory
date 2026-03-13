"""
ingest.py – FastAPI Ingestion-Endpunkte für 2nd Memory.

Endpunkte:
  POST /api/ingest/photos       – 50 Sample-Fotos einlesen
  POST /api/ingest/reviews      – Google Maps Bewertungen einlesen
  POST /api/ingest/saved        – Google Maps Gespeicherte Orte einlesen
  POST /api/ingest/whatsapp     – WhatsApp-Export einlesen (Upload)
  POST /api/ingest/signal       – Signal-Export einlesen (Upload)
  POST /api/ingest/all          – Alle lokalen Quellen auf einmal
  GET  /api/ingest/status       – Anzahl indexierter Dokumente
  GET  /api/ingest/stream/{src} – SSE-Fortschrittsstrom
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------

class IngestResponse(BaseModel):
    source: str
    total: int
    success: int
    errors: int
    message: str


class StatusResponse(BaseModel):
    photos: int
    reviews: int
    saved_places: int
    messages: int
    total: int


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Gibt die Anzahl indexierter Dokumente pro Collection zurück."""
    from backend.rag.store import count_documents
    photos = count_documents("photos")
    reviews = count_documents("reviews")
    saved = count_documents("saved_places")
    msgs = count_documents("messages")
    return StatusResponse(
        photos=photos,
        reviews=reviews,
        saved_places=saved,
        messages=msgs,
        total=photos + reviews + saved + msgs,
    )


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------

@router.post("/photos", response_model=IngestResponse)
async def ingest_photos(reset: bool = False) -> IngestResponse:
    """Liest die 50 Sample-Fotos ein und indexiert sie."""
    try:
        from backend.ingestion.photos import ingest_photos as _ingest
        stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _ingest(reset=reset)
        )
        return IngestResponse(
            source="photos",
            **stats,
            message=f"{stats['success']} Fotos erfolgreich indexiert.",
        )
    except Exception as exc:
        logger.exception("Fehler bei Foto-Ingestion")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Google Reviews
# ---------------------------------------------------------------------------

@router.post("/reviews", response_model=IngestResponse)
async def ingest_reviews(reset: bool = False) -> IngestResponse:
    """Liest Google Maps Bewertungen ein."""
    try:
        from backend.ingestion.google_reviews import ingest_reviews as _ingest
        stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _ingest(reset=reset)
        )
        return IngestResponse(
            source="reviews",
            **stats,
            message=f"{stats['success']} Bewertungen indexiert.",
        )
    except Exception as exc:
        logger.exception("Fehler bei Reviews-Ingestion")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Google Saved Places
# ---------------------------------------------------------------------------

@router.post("/saved", response_model=IngestResponse)
async def ingest_saved(reset: bool = False) -> IngestResponse:
    """Liest Google Maps Gespeicherte Orte ein."""
    try:
        from backend.ingestion.google_saved import ingest_saved_places as _ingest
        stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _ingest(reset=reset)
        )
        return IngestResponse(
            source="saved_places",
            **stats,
            message=f"{stats['success']} gespeicherte Orte indexiert.",
        )
    except Exception as exc:
        logger.exception("Fehler bei Saved-Places-Ingestion")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# WhatsApp Upload
# ---------------------------------------------------------------------------

@router.post("/whatsapp", response_model=IngestResponse)
async def ingest_whatsapp(
    file: UploadFile = File(...),
    chat_name: str | None = None,
    reset: bool = False,
) -> IngestResponse:
    """Nimmt eine WhatsApp-Export-TXT entgegen und indexiert sie."""
    from backend.ingestion.whatsapp import ingest_whatsapp as _ingest

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _ingest(tmp_path, chat_name=chat_name or file.filename, reset=reset)
        )
        return IngestResponse(
            source="whatsapp",
            **stats,
            message=f"{stats['success']} Nachrichten aus WhatsApp indexiert.",
        )
    except Exception as exc:
        logger.exception("Fehler bei WhatsApp-Ingestion")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Signal Upload
# ---------------------------------------------------------------------------

@router.post("/signal", response_model=IngestResponse)
async def ingest_signal(
    file: UploadFile = File(...),
    reset: bool = False,
) -> IngestResponse:
    """Nimmt einen Signal-JSON-Export entgegen und indexiert ihn."""
    from backend.ingestion.signal import ingest_signal as _ingest

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _ingest(tmp_path, reset=reset)
        )
        return IngestResponse(
            source="signal",
            **stats,
            message=f"{stats['success']} Signal-Nachrichten indexiert.",
        )
    except Exception as exc:
        logger.exception("Fehler bei Signal-Ingestion")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Alles auf einmal
# ---------------------------------------------------------------------------

@router.post("/all")
async def ingest_all(reset: bool = False) -> dict:
    """Liest alle verfügbaren lokalen Quellen ein (Fotos, Reviews, Saved Places)."""
    results = {}

    for source, func_path in [
        ("photos", "backend.ingestion.photos.ingest_photos"),
        ("reviews", "backend.ingestion.google_reviews.ingest_reviews"),
        ("saved_places", "backend.ingestion.google_saved.ingest_saved_places"),
    ]:
        try:
            module_path, func_name = func_path.rsplit(".", 1)
            import importlib
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            stats = await asyncio.get_event_loop().run_in_executor(
                None, lambda f=func: f(reset=reset)
            )
            results[source] = stats
        except Exception as exc:
            logger.exception("Fehler bei %s-Ingestion", source)
            results[source] = {"error": str(exc)}

    return results


# ---------------------------------------------------------------------------
# SSE-Fortschrittsstrom
# ---------------------------------------------------------------------------

# Globaler Fortschritts-Speicher (simpel für Einzelnutzer)
_progress: dict[str, dict] = {}


async def _sse_generator(source: str) -> AsyncGenerator[str, None]:
    """Generator für Server-Sent Events."""
    last_seen = None
    timeout = 120  # Sekunden
    elapsed = 0

    while elapsed < timeout:
        current = _progress.get(source)
        if current and current != last_seen:
            last_seen = current
            data = json.dumps(current, ensure_ascii=False)
            yield f"data: {data}\n\n"

            if current.get("done"):
                break

        await asyncio.sleep(0.5)
        elapsed += 0.5

    yield "data: {\"done\": true}\n\n"


@router.get("/stream/{source}")
async def stream_progress(source: str) -> StreamingResponse:
    """SSE-Endpunkt für Echtzeit-Fortschrittsanzeige während der Ingestion."""
    if source not in ("photos", "reviews", "saved", "all"):
        raise HTTPException(status_code=400, detail=f"Unbekannte Quelle: {source}")
    return StreamingResponse(
        _sse_generator(source),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
