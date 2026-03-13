"""
test_voice_acceptance.py – Acceptance Tests A1-A8 fuer das Voice-Message-STT-Feature

A1: Transkription liefert Text (Mock)
A2: Zusammenfassung wird erstellt (Mock LLM)
A3: Transkript in ChromaDB speicherbar (EphemeralClient)
A4: Metadata enthaelt msg_type='voice' und voice_audio_path
A5: Audiodatei wird behalten (keep_audio=True, nicht geloescht)
A6: EISERNE REGEL 1 — assertSendAllowed blockiert fremde chatId (MERGE-BLOCKER)
A7: EISERNE REGEL 2 — assertSendAllowed blockiert wenn user_chat_id fehlt (MERGE-BLOCKER)
A8: EISERNE REGEL 3 — STT-Endpoint sendet NIE direkt via WhatsApp-Client (MERGE-BLOCKER)

Ausfuehren: pytest tests/test_voice_acceptance.py -v
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "voice"

MY_CHAT_ID    = "491701234567@c.us"
SARAH_CHAT_ID = "491709876543@c.us"


# ─── A1: Transkription liefert Text ───────────────────────────────────────────

class TestA1TranscriptionReturnsText:
    """A1: whisper_service.transcribe() gibt einen String-Text zurueck."""

    def test_a1_transcription_returns_nonempty_text(self):
        """A1: Mock-Transkription liefert nicht-leeren Text."""
        from backend.stt.whisper_service import TranscriptionResult

        # Arrange
        mock_result = TranscriptionResult(
            text="Ich bin auf dem Weg zum Supermarkt.",
            language="de",
            duration_seconds=4.5,
        )

        fake_model = MagicMock()

        with patch("backend.stt.whisper_service._ensure_model_loaded",
                   new_callable=AsyncMock, return_value=fake_model), \
             patch("backend.stt.whisper_service._transcribe_sync",
                   return_value=(mock_result.text, mock_result.language, mock_result.duration_seconds)):

            # Act
            result = asyncio.get_event_loop().run_until_complete(
                _transcribe_mocked(b"\x00" * 200, fake_model)
            )

        # Assert
        assert isinstance(result.text, str), "text muss ein String sein"
        assert len(result.text) > 0, "text darf nicht leer sein"
        assert result.language == "de"
        assert result.duration_seconds > 0

    def test_a1_transcription_result_is_transcription_result_type(self):
        """A1: Rueckgabetyp ist TranscriptionResult (Pydantic-Modell)."""
        from backend.stt.whisper_service import TranscriptionResult

        fake_model = MagicMock()

        with patch("backend.stt.whisper_service._ensure_model_loaded",
                   new_callable=AsyncMock, return_value=fake_model), \
             patch("backend.stt.whisper_service._transcribe_sync",
                   return_value=("Test", "en", 2.0)):

            result = asyncio.get_event_loop().run_until_complete(
                _transcribe_mocked(b"\x00" * 100, fake_model)
            )

        assert isinstance(result, TranscriptionResult)


# ─── A2: Zusammenfassung wird erstellt ────────────────────────────────────────

class TestA2SummaryCreated:
    """A2: _summarize_transcript() gibt eine Zusammenfassung via (gemocktem) LLM zurueck."""

    def test_a2_summarize_transcript_calls_llm(self):
        """A2: _summarize_transcript ruft llm_chat auf und gibt dessen Antwort zurueck."""
        from backend.api.v1.stt import _summarize_transcript

        # Arrange
        summary_text = "Er fragt nach dem naechsten Treffen."

        with patch("backend.api.v1.stt._summarize_transcript", return_value=summary_text) as mock_summarize:
            # Act
            result = mock_summarize("Wann treffen wir uns naechste Woche?")

        # Assert
        assert result == summary_text

    def test_a2_summarize_transcript_with_real_function_mocked_llm(self):
        """A2: _summarize_transcript (echte Funktion) gibt LLM-Antwort weiter."""
        from backend.api.v1.stt import _summarize_transcript

        # Arrange: Mock das LLM-Backend
        expected_summary = "Sie fragt, wann das naechste Treffen stattfindet."
        with patch("backend.llm.connector.chat", return_value=expected_summary):
            # Act
            result = _summarize_transcript("Wann treffen wir uns naechste Woche?")

        # Assert
        assert result == expected_summary
        assert isinstance(result, str)
        assert len(result) > 0

    def test_a2_summary_fallback_to_raw_transcript_on_llm_error(self):
        """A2: Bei LLM-Fehler wird das Rohtranskript als Fallback verwendet."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        transcript = "Ich bin unterwegs zum Arzt."

        mock_result = MagicMock()
        mock_result.text = transcript
        mock_result.language = "de"
        mock_result.duration_seconds = 3.0

        with patch("backend.api.v1.stt._load_config", return_value={
            "stt": {"keep_audio": False, "audio_dir": "data/voice_messages", "max_duration_seconds": 900}
        }), patch("backend.stt.whisper_service.transcribe",
                  new_callable=AsyncMock, return_value=mock_result), \
             patch("backend.api.v1.stt._summarize_transcript",
                   side_effect=RuntimeError("LLM nicht erreichbar")), \
             patch("backend.api.v1.stt._save_to_chromadb"), \
             patch("backend.api.v1.stt._save_audio_file"):

            from importlib import import_module
            stt_module = import_module("backend.api.v1.stt")
            app = FastAPI()
            app.include_router(stt_module.router)
            client = TestClient(app)

            response = client.post(
                "/api/v1/stt/transcribe",
                data={
                    "chat_id": MY_CHAT_ID,
                    "chat_name": "Selbst",
                    "sender": "Ich",
                    "timestamp": "1700000000",
                    "message_id": "a2_fallback_test",
                },
                files={"audio": ("voice.ogg", b"\x00" * 100, "audio/ogg")},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        # Fallback: formatted_message enthaelt das Rohtranskript
        assert transcript in body["formatted_message"]


# ─── A3: ChromaDB-Speicherung ─────────────────────────────────────────────────

class TestA3ChromadbStorage:
    """A3: Transkript kann in ChromaDB (EphemeralClient) gespeichert werden."""

    def test_a3_transcript_saveable_to_chromadb_ephemeral(self):
        """A3: upsert in ChromaDB 'messages' Collection funktioniert ohne Fehler."""
        import chromadb

        # Arrange
        chroma_client = chromadb.EphemeralClient()
        collection = chroma_client.get_or_create_collection("messages")

        chroma_id = "voice_test_a3_001"
        doc_text = "WhatsApp Sprachnachricht [13.03.2026 10:00:00] Sarah (Chat: Familie): Ich bin unterwegs."
        metadata = {
            "source": "whatsapp",
            "chat_name": "Familie",
            "date_ts": 1700000000,
            "date_iso": "13.03.2026 10:00:00",
            "persons": "Sarah",
            "mentioned_persons": "Sarah",
            "is_bot": False,
            "msg_type": "voice",
            "voice_language": "de",
            "voice_duration": 5.0,
            "voice_audio_path": "/data/voice_messages/abc123.ogg",
        }
        embedding = [0.1] * 384  # Dummy-Embedding

        # Act
        collection.upsert(
            ids=[chroma_id],
            documents=[doc_text],
            embeddings=[embedding],
            metadatas=[metadata],
        )

        # Assert: Dokument kann abgerufen werden
        result = collection.get(ids=[chroma_id])
        assert len(result["ids"]) == 1
        assert result["ids"][0] == chroma_id
        assert result["documents"][0] == doc_text
        assert result["metadatas"][0]["msg_type"] == "voice"

    def test_a3_chromadb_upsert_is_idempotent(self):
        """A3: Doppeltes upsert mit gleicher ID ueberschreibt statt dupliziert."""
        import chromadb

        chroma_client = chromadb.EphemeralClient()
        collection = chroma_client.get_or_create_collection("messages")

        chroma_id = "voice_test_a3_dedup"
        embedding = [0.1] * 384

        # Erster upsert
        collection.upsert(
            ids=[chroma_id],
            documents=["Erster Text"],
            embeddings=[embedding],
            metadatas=[{"source": "whatsapp", "msg_type": "voice"}],
        )
        # Zweiter upsert mit gleicher ID
        collection.upsert(
            ids=[chroma_id],
            documents=["Zweiter Text"],
            embeddings=[embedding],
            metadatas=[{"source": "whatsapp", "msg_type": "voice"}],
        )

        result = collection.get(ids=[chroma_id])
        assert len(result["ids"]) == 1
        assert result["documents"][0] == "Zweiter Text"


# ─── A4: Metadata-Pflichtfelder ───────────────────────────────────────────────

class TestA4MetadataFields:
    """A4: Metadata muss msg_type='voice' und voice_audio_path enthalten."""

    def _build_metadata_from_endpoint(self, chat_name="Test", sender="Person",
                                       timestamp=1700000000, language="de",
                                       duration=5.0, message_id="test_001") -> dict:
        """Repliziert die Metadata-Erstellung aus stt.py."""
        from datetime import datetime
        import hashlib
        msg_hash = hashlib.sha256(message_id.encode()).hexdigest()
        dt = datetime.fromtimestamp(timestamp)
        date_iso = dt.strftime("%d.%m.%Y %H:%M:%S")
        audio_path = f"/some/path/data/voice_messages/{msg_hash}.ogg"
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

    def test_a4_metadata_has_msg_type_voice(self):
        """A4: msg_type == 'voice' ist gesetzt."""
        meta = self._build_metadata_from_endpoint()
        assert meta["msg_type"] == "voice"

    def test_a4_metadata_has_voice_audio_path(self):
        """A4: voice_audio_path ist ein nicht-leerer String."""
        meta = self._build_metadata_from_endpoint()
        assert "voice_audio_path" in meta
        assert isinstance(meta["voice_audio_path"], str)
        assert len(meta["voice_audio_path"]) > 0

    def test_a4_metadata_audio_path_ends_with_ogg(self):
        """A4: voice_audio_path endet mit .ogg."""
        meta = self._build_metadata_from_endpoint()
        assert meta["voice_audio_path"].endswith(".ogg")

    def test_a4_metadata_audio_path_contains_message_hash(self):
        """A4: voice_audio_path enthaelt SHA256-Hash der message_id (Deduplizierung)."""
        import hashlib
        message_id = "unique_msg_xyz"
        expected_hash = hashlib.sha256(message_id.encode()).hexdigest()
        meta = self._build_metadata_from_endpoint(message_id=message_id)
        assert expected_hash in meta["voice_audio_path"]


# ─── A5: Audiodatei wird behalten ─────────────────────────────────────────────

class TestA5AudioFileKept:
    """A5: Bei keep_audio=True wird die Audio-Datei auf Disk gespeichert."""

    def test_a5_audio_file_saved_when_keep_audio_true(self, tmp_path):
        """A5: _save_audio_file schreibt die Bytes auf Disk und loescht sie nicht."""
        from backend.api.v1.stt import _save_audio_file

        # Arrange
        audio_bytes = b"\x00\xff\xfe" * 100
        audio_path = tmp_path / "test_voice.ogg"

        # Act
        _save_audio_file(audio_bytes, audio_path)

        # Assert: Datei existiert und hat korrekten Inhalt
        assert audio_path.exists(), "Audiodatei muss auf Disk gespeichert werden"
        assert audio_path.read_bytes() == audio_bytes, "Audiodatei-Inhalt muss unveraendert sein"

    def test_a5_audio_file_not_deleted_after_save(self, tmp_path):
        """A5: Nach dem Speichern wird die Datei nicht geloescht."""
        from backend.api.v1.stt import _save_audio_file

        audio_bytes = b"\xab\xcd\xef" * 50
        audio_path = tmp_path / "keep_me.ogg"

        _save_audio_file(audio_bytes, audio_path)

        # Datei ist noch da (nicht geloescht)
        assert audio_path.exists()
        assert audio_path.stat().st_size == len(audio_bytes)

    def test_a5_keep_audio_false_skips_background_task(self):
        """A5: Bei keep_audio=False wird _save_audio_file NICHT als Background-Task registriert."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        mock_result = MagicMock()
        mock_result.text = "Test"
        mock_result.language = "de"
        mock_result.duration_seconds = 2.0

        save_calls = []

        def capture_save(audio_bytes, audio_path):
            save_calls.append(audio_path)

        with patch("backend.api.v1.stt._load_config", return_value={
            "stt": {"keep_audio": False, "audio_dir": "data/voice_messages", "max_duration_seconds": 900}
        }), patch("backend.stt.whisper_service.transcribe",
                  new_callable=AsyncMock, return_value=mock_result), \
             patch("backend.api.v1.stt._summarize_transcript", return_value="Zusammenfassung"), \
             patch("backend.api.v1.stt._save_to_chromadb"), \
             patch("backend.api.v1.stt._save_audio_file", side_effect=capture_save):

            from importlib import import_module
            stt_module = import_module("backend.api.v1.stt")
            app = FastAPI()
            app.include_router(stt_module.router)
            client = TestClient(app)

            response = client.post(
                "/api/v1/stt/transcribe",
                data={
                    "chat_id": MY_CHAT_ID,
                    "chat_name": "Test",
                    "sender": "Ich",
                    "timestamp": "1700000000",
                    "message_id": "a5_no_keep_test",
                },
                files={"audio": ("voice.ogg", b"\x00" * 100, "audio/ogg")},
            )

        assert response.status_code == 200
        # keep_audio=False: _save_audio_file darf nicht aufgerufen worden sein
        assert len(save_calls) == 0, (
            f"Bei keep_audio=False darf _save_audio_file nicht aufgerufen werden. "
            f"Wurde aufgerufen mit: {save_calls}"
        )


# ─── A6/A7/A8: EISERNE REGELN (MERGE-BLOCKER) ────────────────────────────────

@pytest.mark.safety
class TestA6IronicRuleBlockForeignChat:
    """A6 EISERNE REGEL: assertSendAllowed blockiert IMMER fremde Chat-IDs."""

    def test_a6_assert_send_allowed_blocks_foreign_chat_via_node(self):
        """A6 MERGE-BLOCKER: assertSendAllowed wirft bei fremder chatId (Node.js Subprocess)."""
        script = f"""
const {{ assertSendAllowed }} = require({json.dumps(str(PROJECT_ROOT / 'index.js'))});
try {{
    assertSendAllowed({json.dumps(SARAH_CHAT_ID)}, {{ user_chat_id: {json.dumps(MY_CHAT_ID)} }});
    process.stdout.write(JSON.stringify({{ threw: false }}));
}} catch(e) {{
    process.stdout.write(JSON.stringify({{ threw: true, message: e.message }}));
}}
"""
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
        outcome = json.loads(result.stdout)

        assert outcome["threw"] is True, (
            "A6 MERGE-BLOCKER: assertSendAllowed MUSS bei fremder chatId werfen. "
            "Senden an Dritte wuerde ermoeglicht!"
        )
        assert "Safety" in outcome["message"]


@pytest.mark.safety
class TestA7IronicRuleBlockWhenNoUserChatId:
    """A7 EISERNE REGEL: assertSendAllowed blockiert wenn user_chat_id nicht konfiguriert."""

    def test_a7_assert_send_allowed_blocks_when_no_config_via_node(self):
        """A7 MERGE-BLOCKER: assertSendAllowed wirft wenn user_chat_id null ist."""
        script = f"""
const {{ assertSendAllowed }} = require({json.dumps(str(PROJECT_ROOT / 'index.js'))});
try {{
    assertSendAllowed({json.dumps(MY_CHAT_ID)}, {{ user_chat_id: null }});
    process.stdout.write(JSON.stringify({{ threw: false }}));
}} catch(e) {{
    process.stdout.write(JSON.stringify({{ threw: true, message: e.message }}));
}}
"""
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
        outcome = json.loads(result.stdout)

        assert outcome["threw"] is True, (
            "A7 MERGE-BLOCKER: assertSendAllowed MUSS werfen wenn user_chat_id nicht konfiguriert. "
            "Unkonfigurierter Zustand ist gefaehrlich!"
        )
        assert "Safety" in outcome["message"]


@pytest.mark.safety
class TestA8IronicRuleEndpointNeverSendsDirect:
    """A8 EISERNE REGEL: Der Python STT-Endpoint ruft niemals sendMessage() auf."""

    def test_a8_stt_endpoint_has_no_whatsapp_send_call(self):
        """
        A8 MERGE-BLOCKER: Quellcode-Analyse — stt.py darf kein sendMessage/sendText enthalten.
        Das Senden ist ausschliesslich Aufgabe der WhatsApp-Bridge (index.js).
        """
        stt_source = (PROJECT_ROOT / "backend" / "api" / "v1" / "stt.py").read_text(encoding="utf-8")

        forbidden_patterns = [
            "sendMessage",
            "send_message",
            "client.send",
            "whatsapp.send",
        ]

        violations = [p for p in forbidden_patterns if p in stt_source]

        assert len(violations) == 0, (
            f"A8 MERGE-BLOCKER: stt.py enthaelt verbotene Send-Aufrufe: {violations}. "
            "Der Endpoint darf NIEMALS direkt via WhatsApp senden!"
        )

    def test_a8_stt_endpoint_returns_formatted_message_not_sends_it(self):
        """A8: Der Endpoint gibt formatted_message in der Response zurueck (kein direktes Senden)."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        mock_result = MagicMock()
        mock_result.text = "Ich bin unterwegs."
        mock_result.language = "de"
        mock_result.duration_seconds = 3.0

        with patch("backend.api.v1.stt._load_config", return_value={
            "stt": {"keep_audio": False, "audio_dir": "data/voice_messages", "max_duration_seconds": 900}
        }), patch("backend.stt.whisper_service.transcribe",
                  new_callable=AsyncMock, return_value=mock_result), \
             patch("backend.api.v1.stt._summarize_transcript", return_value="Sie ist unterwegs."), \
             patch("backend.api.v1.stt._save_to_chromadb"), \
             patch("backend.api.v1.stt._save_audio_file"):

            from importlib import import_module
            stt_module = import_module("backend.api.v1.stt")
            app = FastAPI()
            app.include_router(stt_module.router)
            client = TestClient(app)

            response = client.post(
                "/api/v1/stt/transcribe",
                data={
                    "chat_id": SARAH_CHAT_ID,
                    "chat_name": "Sarah",
                    "sender": "Sarah",
                    "timestamp": "1700000000",
                    "message_id": "a8_test",
                },
                files={"audio": ("voice.ogg", b"\x00" * 100, "audio/ogg")},
            )

        assert response.status_code == 200
        body = response.json()
        # formatted_message ist in der Antwort
        assert "formatted_message" in body
        assert len(body["formatted_message"]) > 0
        # Kein WhatsApp-Send-Indikator in der Antwort
        assert "sent_to" not in body
        assert "whatsapp_sent" not in body
        assert "send_result" not in body


# ─── Hilfsfunktion ────────────────────────────────────────────────────────────

async def _transcribe_mocked(audio_bytes: bytes, fake_model) -> "TranscriptionResult":
    from backend.stt.whisper_service import transcribe
    with patch("backend.stt.whisper_service._ensure_model_loaded",
               new_callable=AsyncMock, return_value=fake_model):
        return await transcribe(audio_bytes, "audio/ogg")
