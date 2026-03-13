"""
whisper_service.py – Lazy-loading faster-whisper STT service.

Transkribiert Audio-Dateien mit faster-whisper auf CPU (int8).
Modell-Fallback: large-v3 → medium → small (konfigurierbar via config.yaml).
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_whisper_model: Any = None
_whisper_lock = asyncio.Lock()


def _load_config() -> dict:
    """Liest STT-Konfiguration aus config.yaml."""
    cfg_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f).get("stt", {})


class TranscriptionResult(BaseModel):
    """Ergebnis einer Spracherkennung."""
    text: str
    language: str
    duration_seconds: float


def _load_model_sync(model_name: str, device: str, compute_type: str) -> Any:
    """Lädt ein faster-whisper Modell synchron (für run_in_executor).

    Args:
        model_name: Modell-Name (z.B. 'large-v3', 'medium', 'small').
        device: Gerät ('cpu' oder 'cuda').
        compute_type: Berechnungstyp ('int8', 'float16', etc.).

    Returns:
        Geladenes WhisperModel-Objekt.
    """
    from faster_whisper import WhisperModel
    logger.info("[STT] Lade Whisper-Modell: %s (device=%s, compute=%s)", model_name, device, compute_type)
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _transcribe_sync(model: Any, audio_path: str) -> tuple[str, str, float]:
    """Führt Transkription synchron aus (blockierend, für run_in_executor).

    Args:
        model: Geladenes WhisperModel-Objekt.
        audio_path: Pfad zur Audio-Datei.

    Returns:
        Tuple aus (transkribierter Text, Sprache, Dauer in Sekunden).
    """
    segments, info = model.transcribe(audio_path, beam_size=5)
    text = " ".join(seg.text for seg in segments).strip()
    return text, info.language, info.duration


async def _ensure_model_loaded(cfg: dict) -> Any:
    """Stellt sicher dass das Whisper-Modell geladen ist (mit Fallback-Kette).

    Args:
        cfg: STT-Konfigurationsdict aus config.yaml.

    Returns:
        Geladenes WhisperModel-Objekt.
    """
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    device = cfg.get("device", "cpu")
    compute_type = cfg.get("compute_type", "int8")
    primary = cfg.get("model", "large-v3")
    fallbacks: list[str] = cfg.get("fallback_models", ["medium", "small"])
    loop = asyncio.get_event_loop()

    for model_name in [primary] + fallbacks:
        try:
            _whisper_model = await loop.run_in_executor(
                None, _load_model_sync, model_name, device, compute_type
            )
            logger.info("[STT] Modell '%s' erfolgreich geladen.", model_name)
            return _whisper_model
        except Exception as exc:
            logger.warning("[STT] Modell '%s' konnte nicht geladen werden: %s — versuche Fallback.", model_name, exc)

    raise RuntimeError("[STT] Kein Whisper-Modell konnte geladen werden (alle Fallbacks erschoepft).")


async def transcribe(audio_bytes: bytes, mimetype: str = "audio/ogg") -> TranscriptionResult:
    """Transkribiert Audio-Bytes mit faster-whisper.

    Schreibt die Bytes in eine temporaere Datei, damit faster-whisper
    einen Dateipfad erhaelt. Nutzt asyncio.Lock fuer sequentielle CPU-Nutzung.

    Args:
        audio_bytes: Rohe Audio-Daten (OGG, OPUS, MP3, etc.).
        mimetype: MIME-Typ des Audios (nur fuer Logging).

    Returns:
        TranscriptionResult mit text, language und duration_seconds.
    """
    cfg = _load_config()
    max_duration = cfg.get("max_duration_seconds", 900)

    suffix = ".ogg" if "ogg" in mimetype or "opus" in mimetype else ".mp3"

    async with _whisper_lock:
        model = await _ensure_model_loaded(cfg)

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            loop = asyncio.get_event_loop()
            text, language, duration = await loop.run_in_executor(
                None, _transcribe_sync, model, tmp.name
            )

    if duration > max_duration:
        logger.warning("[STT] Audio-Dauer %ds ueberschreitet Maximum %ds.", int(duration), max_duration)

    logger.info("[STT] Transkription abgeschlossen: %s (%.1fs, Sprache: %s)", text[:60], duration, language)
    return TranscriptionResult(text=text, language=language, duration_seconds=duration)
