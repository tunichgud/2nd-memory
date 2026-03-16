"""
ingest.py – /api/v1/ingest/*

Ingestion-Endpunkte für Fotos, Nachrichten und Google-Daten.
GPS und Datums-Metadaten bleiben unverändert.
"""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
import aiosqlite

from backend.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ingest", tags=["v1/ingest"])


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status_v1(user_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Anzahl indexierter Dokumente pro Collection für einen User."""
    from backend.rag.store_v2 import count_documents_for_user
    return {
        col: count_documents_for_user(col, user_id)
        for col in ["photos", "reviews", "saved_places", "messages"]
    }


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------

class PhotoIngestRequest(BaseModel):
    user_id: str
    reset: bool = False


class PhotoDescribeRequest(BaseModel):
    """
    Backend beschreibt das Bild via Ollama, gibt den Text zurück.
    """
    user_id: str
    filename: str


class PhotoSubmitRequest(BaseModel):
    """Foto-Datensatz einreichen."""
    user_id: str
    filename: str
    description: str = ""
    date_iso: str = ""
    date_ts: int = 0
    lat: float = 0.0
    lon: float = 0.0
    place_name: str = ""
    persons: str = ""
    cluster: str = ""
    reset: bool = False


@router.post("/photos/describe")
async def describe_photo_v1(
    req: PhotoDescribeRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Schritt 1 des Foto-Ingestion-Flows:
    Server gibt die KI-Bildbeschreibung (Klartext) zurück.
    Das Frontend maskiert sie und ruft dann /photos/submit auf.
    """
    from backend.ingestion.photos import _find_photo_in_dir, _find_photo_in_zips
    from backend.llm.connector import describe_image, get_cfg
    import yaml

    cfg = get_cfg()
    base = Path(__file__).resolve().parents[3]
    photos_dir = base / cfg["paths"]["photos_dir"]
    takeout_root = base / "takeout"

    result = _find_photo_in_dir(req.filename, photos_dir)
    if result is None:
        result = _find_photo_in_zips(req.filename, takeout_root)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Foto nicht gefunden: {req.filename}")

    image_bytes, _ = result
    try:
        description = await asyncio.get_event_loop().run_in_executor(
            None, lambda: describe_image(image_bytes)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vision-Fehler: {exc}")

    return {"filename": req.filename, "description": description}


@router.post("/photos/submit")
async def submit_photo_v1(
    req: PhotoSubmitRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Schritt 2: Speichert das Foto mit Beschreibung in ChromaDB.
    """
    from backend.rag.store_v2 import upsert_documents_v2
    from backend.rag.embedder import embed_single

    # Dokument-Text aufbauen
    parts = [f"Foto: {req.filename}"]
    if req.date_iso:
        parts.append(f"Datum: {req.date_iso}")
    if req.place_name:
        parts.append(f"Ort: {req.place_name}")
    if req.lat != 0.0:
        parts.append(f"Koordinaten: {req.lat:.5f}°N, {req.lon:.5f}°E")
    if req.persons:
        parts.append(f"Personen: {req.persons}")
    if req.description:
        parts.append(f"Bildbeschreibung: {req.description}")
    doc_text = "\n".join(parts)

    embedding = await asyncio.get_event_loop().run_in_executor(
        None, lambda: embed_single(doc_text)
    )

    meta = {
        "source": "google_photos",
        "user_id": req.user_id,
        "filename": req.filename,
        "date_ts": req.date_ts,
        "date_iso": req.date_iso,
        "lat": req.lat,
        "lon": req.lon,
        "place_name": req.place_name,
        "persons": req.persons,
        "cluster": req.cluster,
    }

    upsert_documents_v2(
        "photos",
        [f"photo_{req.user_id}_{req.filename}"],
        [doc_text],
        [embedding],
        [meta],
    )
    return {"status": "ok", "filename": req.filename}


# ---------------------------------------------------------------------------
# Google Reviews + Saved Places (keine Biometrie, kein Consent nötig)
# ---------------------------------------------------------------------------

@router.post("/reviews")
async def ingest_reviews_v1(user_id: str, reset: bool = False, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    from backend.ingestion.google_reviews import ingest_reviews
    stats = await asyncio.get_event_loop().run_in_executor(
        None, lambda: ingest_reviews(reset=reset, user_id=user_id)
    )
    return {"source": "reviews", **stats}


@router.post("/saved")
async def ingest_saved_v1(user_id: str, reset: bool = False, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    from backend.ingestion.google_saved import ingest_saved_places
    stats = await asyncio.get_event_loop().run_in_executor(
        None, lambda: ingest_saved_places(reset=reset, user_id=user_id)
    )
    return {"source": "saved_places", **stats}


# ---------------------------------------------------------------------------
# Nachrichten – bereits maskierter Text
# ---------------------------------------------------------------------------

@router.post("/messages")
async def ingest_messages_v1(
    user_id: str,
    source_type: str = "whatsapp",   # "whatsapp" | "signal"
    chat_name: str | None = None,
    reset: bool = False,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Nimmt eine Nachrichtendatei entgegen und indexiert sie in ChromaDB.
    """
    content = await file.read()
    suffix = ".json" if source_type == "signal" else ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        if source_type == "whatsapp":
            from backend.ingestion.whatsapp import ingest_whatsapp
            stats = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ingest_whatsapp(
                    tmp_path,
                    chat_name=chat_name or file.filename,
                    reset=reset,
                    user_id=user_id,
                ),
            )
        else:
            from backend.ingestion.signal import ingest_signal
            stats = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ingest_signal(tmp_path, reset=reset, user_id=user_id),
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"source": source_type, **stats}
