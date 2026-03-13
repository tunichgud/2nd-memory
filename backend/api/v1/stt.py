"""
stt.py – POST /api/v1/stt/transcribe

Nimmt WhatsApp-Sprachnachrichten entgegen, transkribiert sie mit Whisper,
fasst das Transkript per LLM zusammen und speichert es in ChromaDB.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, Form, UploadFile, File
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stt", tags=["stt"])


def _load_config() -> dict:
    """Liest Konfiguration aus config.yaml."""
    cfg_path = Path(__file__).resolve().parents[3] / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TranscribeResponse(BaseModel):
    """Antwort des STT-Endpoints."""
    status: str
    formatted_message: str
    transcript: Optional[str] = None
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    chroma_id: Optional[str] = None


def _build_formatted_message(
    sender: str,
    chat_name: str,
    uhrzeit: str,
    summary: str,
    duration_seconds: float,
    language: str,
) -> str:
    """Baut die formatierte STT-Zusammenfassungsnachricht auf.

    Args:
        sender: Name des Absenders.
        chat_name: Name des Chats.
        uhrzeit: Formatierte Uhrzeit (HH:MM).
        summary: LLM-generierte Zusammenfassung.
        duration_seconds: Dauer der Sprachnachricht in Sekunden.
        language: Erkannte Sprache (ISO-Code).

    Returns:
        Formatierter Nachrichtentext.
    """
    mins = int(duration_seconds // 60)
    secs = int(duration_seconds % 60)
    lang_upper = language.upper() if language else "?"
    return (
        f"[STT] Sprachnachricht von {sender} (Chat: {chat_name}, {uhrzeit})\n\n"
        f"{summary}\n\n"
        f"[Dauer: {mins}:{secs:02d} | Sprache: {lang_upper}]"
    )


def _summarize_transcript(transcript: str) -> str:
    """Fasst ein Transkript per LLM in 1-3 Saetzen zusammen.

    Args:
        transcript: Rohes Transkript der Sprachnachricht.

    Returns:
        LLM-generierte Zusammenfassung.
    """
    from backend.llm.connector import chat as llm_chat
    prompt = (
        "Fasse diese WhatsApp-Sprachnachricht in 1-3 Saetzen zusammen. "
        "Schreibe in der 3. Person (z.B. \"Sie/Er fragt...\"). "
        "Sei praezise und natuerlich. Antworte nur mit der Zusammenfassung, ohne Erklaerungen.\n\n"
        f"Transkript:\n{transcript}"
    )
    return llm_chat([{"role": "user", "content": prompt}])


def _save_to_chromadb(
    chroma_id: str,
    doc_text: str,
    metadata: dict,
) -> None:
    """Speichert Transkript in ChromaDB Collection 'messages'.

    Args:
        chroma_id: Eindeutige Dokument-ID.
        doc_text: Einzuspeichernder Text.
        metadata: Metadaten fuer das Dokument.
    """
    from backend.rag.embedder import embed_single
    from backend.rag.store_v2 import upsert_documents_v2
    embedding = embed_single(doc_text)
    upsert_documents_v2(
        "messages",
        [chroma_id],
        [doc_text],
        [embedding],
        [metadata],
    )
    logger.info("[STT] Transkript in ChromaDB gespeichert: %s", chroma_id)


def _save_audio_file(audio_bytes: bytes, audio_path: Path) -> None:
    """Speichert Audio-Bytes auf Disk.

    Args:
        audio_bytes: Rohe Audio-Daten.
        audio_path: Zielpfad fuer die Datei.
    """
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(audio_bytes)
    logger.info("[STT] Audiodatei gespeichert: %s", audio_path)


@router.get("/health")
async def stt_health() -> dict:
    """Health-Check fuer den STT-Service."""
    return {"status": "ok", "service": "stt", "phase": 3}


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_voice_message(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    chat_id: str = Form(...),
    chat_name: str = Form(...),
    sender: str = Form(...),
    timestamp: int = Form(...),
    message_id: str = Form(...),
    duration: Optional[float] = Form(default=None),
) -> TranscribeResponse:
    """Transkribiert eine WhatsApp-Sprachnachricht und gibt eine formatierte Zusammenfassung zurueck.

    Args:
        background_tasks: FastAPI BackgroundTasks fuer async Speicherung.
        audio: Hochgeladene Audio-Datei (OGG/OPUS/MP4 etc.).
        chat_id: WhatsApp Chat-ID des Absenders.
        chat_name: Anzeigename des Chats.
        sender: Anzeigename des Absenders.
        timestamp: Unix-Timestamp der Nachricht.
        message_id: Eindeutige WhatsApp Message-ID fuer Deduplizierung.
        duration: Optionale Dauer der Sprachnachricht in Sekunden.

    Returns:
        TranscribeResponse mit formatted_message und Transkriptionsdetails.
    """
    cfg = _load_config()
    stt_cfg = cfg.get("stt", {})
    base_dir = Path(__file__).resolve().parents[3]

    # Deduplizierungs-ID aus message_id ableiten
    msg_hash = hashlib.sha256(message_id.encode()).hexdigest()
    chroma_id = f"voice_{msg_hash[:8]}"

    dt = datetime.fromtimestamp(timestamp)
    uhrzeit = dt.strftime("%H:%M")
    date_iso = dt.strftime("%d.%m.%Y %H:%M:%S")

    audio_bytes = await audio.read()
    mimetype = audio.content_type or "audio/ogg"

    # Fehler-Nachrichtenformat fuer Exception-Handler
    error_msg = (
        f"[STT] Fehler bei Sprachnachricht von {sender} (Chat: {chat_name}, {uhrzeit})\n\n"
        "Transkription fehlgeschlagen."
    )

    try:
        from backend.stt.whisper_service import transcribe
        result = await transcribe(audio_bytes, mimetype)
    except Exception as exc:
        logger.error("[STT] Transkription fehlgeschlagen fuer %s: %s", message_id, exc)
        return TranscribeResponse(
            status="error",
            formatted_message=error_msg,
        )

    # LLM-Zusammenfassung (blockierend, in Executor)
    try:
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(None, _summarize_transcript, result.text)
    except Exception as exc:
        logger.warning("[STT] LLM-Zusammenfassung fehlgeschlagen: %s — verwende Rohtranskript.", exc)
        summary = result.text

    formatted = _build_formatted_message(
        sender=sender,
        chat_name=chat_name,
        uhrzeit=uhrzeit,
        summary=summary,
        duration_seconds=result.duration_seconds,
        language=result.language,
    )

    # Audio-Datei speichern (optional, Background-Task)
    audio_dir = base_dir / stt_cfg.get("audio_dir", "data/voice_messages")
    audio_file_path = audio_dir / f"{msg_hash}.ogg"
    if stt_cfg.get("keep_audio", True):
        background_tasks.add_task(_save_audio_file, audio_bytes, audio_file_path)

    # ChromaDB-Speicherung (Background-Task)
    doc_text = f"WhatsApp Sprachnachricht [{date_iso}] {sender} (Chat: {chat_name}): {result.text}"
    metadata = {
        "source": "whatsapp",
        "chat_name": chat_name,
        "date_ts": timestamp,
        "date_iso": date_iso,
        "persons": sender,
        "mentioned_persons": sender,
        "is_bot": False,
        "msg_type": "voice",
        "voice_language": result.language,
        "voice_duration": result.duration_seconds,
        "voice_audio_path": str(audio_file_path),
    }
    background_tasks.add_task(_save_to_chromadb, chroma_id, doc_text, metadata)

    logger.info("[STT] Verarbeitung abgeschlossen fuer %s (%s, %.1fs)", sender, result.language, result.duration_seconds)

    return TranscribeResponse(
        status="success",
        formatted_message=formatted,
        transcript=result.text,
        language=result.language,
        duration_seconds=result.duration_seconds,
        chroma_id=chroma_id,
    )
