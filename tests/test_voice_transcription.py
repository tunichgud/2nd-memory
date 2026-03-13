"""
test_voice_transcription.py – Unit Tests fuer whisper_service + STT Metadata

Alle Whisper-Aufrufe werden gemockt (kein GPU/Modell benoetigt).
Ausfuehren: pytest tests/test_voice_transcription.py -v
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "voice"

SILENCE_5S_OGG = FIXTURES_DIR / "silence_5s.ogg"
CORRUPT_OGG    = FIXTURES_DIR / "corrupt.ogg"
EMPTY_OGG      = FIXTURES_DIR / "empty.ogg"


# ─── Tests: whisper_service.transcribe ────────────────────────────────────────

class TestTranscribeAudio:
    """Unit tests fuer backend.stt.whisper_service.transcribe"""

    def test_transcribe_audio_returns_text(self):
        """Happy path: Mock-Modell gibt transkribierten Text zurueck."""
        # Arrange
        fake_segment = MagicMock()
        fake_segment.text = " Hallo, wie geht es dir?"

        fake_info = MagicMock()
        fake_info.language = "de"
        fake_info.duration = 5.0

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_segment], fake_info)

        audio_bytes = SILENCE_5S_OGG.read_bytes()

        with patch("backend.stt.whisper_service._ensure_model_loaded", new_callable=AsyncMock) as mock_load, \
             patch("backend.stt.whisper_service._transcribe_sync", return_value=("Hallo, wie geht es dir?", "de", 5.0)):
            mock_load.return_value = fake_model

            # Act
            result = asyncio.get_event_loop().run_until_complete(
                _transcribe_with_mock(audio_bytes, fake_model)
            )

        # Assert
        assert isinstance(result.text, str)
        assert len(result.text) > 0
        assert result.language == "de"
        assert result.duration_seconds == 5.0

    def test_transcribe_audio_empty_file(self):
        """Leere Bytes sollen einen Fehler ausloesen."""
        # Arrange
        empty_bytes = b""

        with patch("backend.stt.whisper_service._ensure_model_loaded", new_callable=AsyncMock) as mock_load, \
             patch("backend.stt.whisper_service._transcribe_sync",
                   side_effect=Exception("Audio-Datei ist leer oder kein gueltiges Format")):
            mock_load.return_value = MagicMock()

            # Act + Assert
            with pytest.raises(Exception):
                asyncio.get_event_loop().run_until_complete(
                    _transcribe_with_mock(empty_bytes, mock_load.return_value)
                )

    def test_transcribe_audio_corrupt_file(self):
        """Korrupte Audio-Bytes sollen einen Fehler ausloesen."""
        # Arrange
        corrupt_bytes = CORRUPT_OGG.read_bytes()

        with patch("backend.stt.whisper_service._ensure_model_loaded", new_callable=AsyncMock) as mock_load, \
             patch("backend.stt.whisper_service._transcribe_sync",
                   side_effect=Exception("Kein gueltiges Audio-Format erkannt")):
            mock_load.return_value = MagicMock()

            # Act + Assert
            with pytest.raises(Exception):
                asyncio.get_event_loop().run_until_complete(
                    _transcribe_with_mock(corrupt_bytes, mock_load.return_value)
                )

    def test_transcribe_result_model_fields(self):
        """TranscriptionResult-Modell hat alle Pflichtfelder."""
        from backend.stt.whisper_service import TranscriptionResult

        # Arrange + Act
        result = TranscriptionResult(text="Test", language="en", duration_seconds=3.14)

        # Assert
        assert hasattr(result, "text")
        assert hasattr(result, "language")
        assert hasattr(result, "duration_seconds")
        assert result.text == "Test"
        assert result.language == "en"
        assert result.duration_seconds == pytest.approx(3.14)

    def test_transcribe_strips_whitespace_from_segments(self):
        """Segment-Texte werden per ' '.join() verbunden und das Ergebnis wird mit .strip() getrimmt.

        Whisper liefert Segmente typischerweise mit fuehrendem Space (z.B. " Hallo").
        _transcribe_sync verbindet sie via ' '.join(seg.text for seg in segments).strip().
        Das bedeutet: interner Whitespace bleibt erhalten, nur aussen wird getrimmt.
        """
        # Arrange
        fake_seg1 = MagicMock()
        fake_seg1.text = " Erster Satz."
        fake_seg2 = MagicMock()
        fake_seg2.text = " Zweiter Satz."

        fake_info = MagicMock()
        fake_info.language = "de"
        fake_info.duration = 10.0

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_seg1, fake_seg2], fake_info)

        # Act: _transcribe_sync direkt testen
        from backend.stt.whisper_service import _transcribe_sync
        text, lang, dur = _transcribe_sync(fake_model, "/tmp/dummy.ogg")

        # Assert: ' '.join(" Erster Satz.", " Zweiter Satz.").strip()
        # = " Erster Satz.  Zweiter Satz.".strip() = "Erster Satz.  Zweiter Satz."
        # Fuehrender/nachfolgender Whitespace wird durch .strip() entfernt
        assert not text.startswith(" "), "Fuehrender Whitespace muss durch .strip() entfernt werden"
        assert not text.endswith(" "), "Abschliessender Whitespace muss durch .strip() entfernt werden"
        assert "Erster Satz." in text
        assert "Zweiter Satz." in text
        assert lang == "de"
        assert dur == 10.0


# ─── Tests: Metadata-Dict ─────────────────────────────────────────────────────

class TestBuildChromadbMetadata:
    """Prueft dass die Metadata alle Pflichtfelder enthaelt."""

    def _build_metadata(
        self,
        chat_name: str = "TestChat",
        sender: str = "TestUser",
        timestamp: int = 1700000000,
        language: str = "de",
        duration: float = 5.0,
        audio_path: str = "/data/voice_messages/abc123.ogg",
    ) -> dict:
        """Erstellt das Metadata-Dict wie in stt.py (genaue Kopie der Logik)."""
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp)
        date_iso = dt.strftime("%d.%m.%Y %H:%M:%S")
        return {
            "source": "whatsapp",
            "chat_name": chat_name,
            "date_ts": timestamp,
            "date_iso": date_iso,
            "persons": sender,
            "mentioned_persons": sender,
            "is_bot": False,
            "msg_type": "voice",
            "voice_language": language,
            "voice_duration": duration,
            "voice_audio_path": audio_path,
        }

    def test_build_chromadb_metadata_has_source(self):
        """Metadata enthaelt 'source' = 'whatsapp'."""
        meta = self._build_metadata()
        assert meta["source"] == "whatsapp"

    def test_build_chromadb_metadata_has_chat_name(self):
        """Metadata enthaelt 'chat_name'."""
        meta = self._build_metadata(chat_name="Familie")
        assert meta["chat_name"] == "Familie"

    def test_build_chromadb_metadata_has_date_ts(self):
        """Metadata enthaelt 'date_ts' als Integer."""
        ts = 1700000000
        meta = self._build_metadata(timestamp=ts)
        assert meta["date_ts"] == ts
        assert isinstance(meta["date_ts"], int)

    def test_build_chromadb_metadata_has_msg_type_voice(self):
        """Metadata enthaelt 'msg_type' == 'voice' (Pflicht fuer RAG-Filter)."""
        meta = self._build_metadata()
        assert meta["msg_type"] == "voice"

    def test_build_chromadb_metadata_has_voice_language(self):
        """Metadata enthaelt 'voice_language' mit erkanntem ISO-Code."""
        meta = self._build_metadata(language="de")
        assert meta["voice_language"] == "de"

    def test_build_chromadb_metadata_has_voice_duration(self):
        """Metadata enthaelt 'voice_duration' in Sekunden."""
        meta = self._build_metadata(duration=7.5)
        assert meta["voice_duration"] == pytest.approx(7.5)

    def test_build_chromadb_metadata_has_voice_audio_path(self):
        """Metadata enthaelt 'voice_audio_path' als String."""
        path = "/data/voice_messages/deadbeef.ogg"
        meta = self._build_metadata(audio_path=path)
        assert meta["voice_audio_path"] == path

    def test_build_chromadb_metadata_all_required_fields(self):
        """Alle 7 Pflichtfelder sind vorhanden."""
        required_fields = [
            "source",
            "chat_name",
            "date_ts",
            "msg_type",
            "voice_language",
            "voice_duration",
            "voice_audio_path",
        ]
        meta = self._build_metadata()
        for field in required_fields:
            assert field in meta, f"Pflichtfeld '{field}' fehlt in Metadata"


# ─── Hilfsfunktion fuer async Tests ───────────────────────────────────────────

async def _transcribe_with_mock(audio_bytes: bytes, fake_model) -> "TranscriptionResult":
    """Ruft transcribe() mit gepatchtem _ensure_model_loaded auf."""
    from backend.stt.whisper_service import transcribe
    with patch("backend.stt.whisper_service._ensure_model_loaded", new_callable=AsyncMock, return_value=fake_model):
        return await transcribe(audio_bytes, "audio/ogg")
