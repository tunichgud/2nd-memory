"""
test_voice_send_safety.py – KRITISCHE Safety Tests fuer assertSendAllowed + STT Endpoint

Diese Tests sind Merge-Blocker. Kein Merge wenn auch nur ein Test hier fehlschlaegt.

Prueft:
  - assertSendAllowed() blockiert fremde Chat-IDs
  - assertSendAllowed() erlaubt nur die eigene user_chat_id
  - assertSendAllowed() wirft bei fehlender Konfiguration
  - Der STT-Endpoint sendet NICHT selbst — gibt nur formatted_message zurueck

Ausfuehren: pytest tests/test_voice_send_safety.py -v -m safety
"""
from __future__ import annotations

import subprocess
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_JS = PROJECT_ROOT / "index.js"

MY_CHAT_ID     = "491701234567@c.us"
SARAH_CHAT_ID  = "491709876543@c.us"
GROUP_CHAT_ID  = "123456789@g.us"


# ─── assertSendAllowed via Node.js subprocess ─────────────────────────────────

def _run_node_assertion(chatId: str | None, user_chat_id: str | None) -> dict:
    """
    Fuehrt assertSendAllowed in einem Node.js-Subprocess aus und gibt
    {'threw': bool, 'message': str} zurueck.
    """
    script = f"""
const {{ assertSendAllowed }} = require({json.dumps(str(INDEX_JS))});
const config = {{ user_chat_id: {json.dumps(user_chat_id)} }};
const chatId = {json.dumps(chatId)};
try {{
    assertSendAllowed(chatId, config);
    process.stdout.write(JSON.stringify({{ threw: false, message: '' }}));
    process.exit(0);
}} catch (err) {{
    process.stdout.write(JSON.stringify({{ threw: true, message: err.message }}));
    process.exit(0);
}}
"""
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


@pytest.mark.safety
class TestAssertSendAllowed:
    """Testet assertSendAllowed() direkt via Node.js-Subprocess aus index.js."""

    def test_assertSendAllowed_blocks_foreign_chat(self):
        """MERGE-BLOCKER: assertSendAllowed wirft Exception wenn chatId != user_chat_id."""
        # Arrange + Act
        outcome = _run_node_assertion(SARAH_CHAT_ID, MY_CHAT_ID)

        # Assert
        assert outcome["threw"] is True, (
            "assertSendAllowed muss Exception werfen wenn chatId eine fremde ID ist. "
            f"Ausgabe: {outcome}"
        )
        assert "Safety" in outcome["message"], (
            f"Error-Message muss 'Safety' enthalten, war: '{outcome['message']}'"
        )

    def test_assertSendAllowed_blocks_group_chat(self):
        """assertSendAllowed blockiert Gruppenchats."""
        outcome = _run_node_assertion(GROUP_CHAT_ID, MY_CHAT_ID)
        assert outcome["threw"] is True
        assert "Safety" in outcome["message"]

    def test_assertSendAllowed_allows_self_chat(self):
        """MERGE-BLOCKER: assertSendAllowed wirft KEINEN Fehler wenn chatId == user_chat_id."""
        # Arrange + Act
        outcome = _run_node_assertion(MY_CHAT_ID, MY_CHAT_ID)

        # Assert
        assert outcome["threw"] is False, (
            f"assertSendAllowed darf KEINEN Fehler werfen fuer eigene Chat-ID. "
            f"Unerwarteter Error: '{outcome['message']}'"
        )

    def test_assertSendAllowed_blocks_when_no_user_chat_id(self):
        """MERGE-BLOCKER: assertSendAllowed wirft Exception wenn user_chat_id nicht konfiguriert ist."""
        # Arrange + Act
        outcome = _run_node_assertion(MY_CHAT_ID, None)

        # Assert
        assert outcome["threw"] is True, (
            "assertSendAllowed muss Exception werfen wenn user_chat_id == null."
        )
        assert "Safety" in outcome["message"], (
            f"Error-Message muss 'Safety' enthalten, war: '{outcome['message']}'"
        )

    def test_assertSendAllowed_error_message_mentions_blocked_chat(self):
        """Error-Message nennt die geblockte chatId fuer Nachvollziehbarkeit."""
        outcome = _run_node_assertion(SARAH_CHAT_ID, MY_CHAT_ID)
        assert outcome["threw"] is True
        assert SARAH_CHAT_ID in outcome["message"], (
            f"Error-Message soll die geblockte ID '{SARAH_CHAT_ID}' nennen. "
            f"Tatsaechliche Message: '{outcome['message']}'"
        )

    def test_assertSendAllowed_error_starts_with_safety_prefix(self):
        """Error-Message beginnt mit 'Safety:' — Voraussetzung fuer HTTP-403-Erkennung im Endpoint."""
        outcome = _run_node_assertion(SARAH_CHAT_ID, MY_CHAT_ID)
        assert outcome["threw"] is True
        assert outcome["message"].startswith("Safety:"), (
            f"Error-Message muss mit 'Safety:' beginnen fuer 403-Erkennung. "
            f"War: '{outcome['message']}'"
        )


# ─── STT Endpoint: sendet NICHT selbst ────────────────────────────────────────

@pytest.mark.safety
class TestSttEndpointSendTargetIsSelfOnly:
    """
    Der /api/v1/stt/transcribe Endpoint gibt formatted_message zurueck.
    Das SENDEN ist ausschliesslich Aufgabe der WhatsApp-Bridge (index.js).
    Der Endpoint selbst ruft kein client.sendMessage() auf.
    """

    def test_stt_endpoint_returns_formatted_message_in_response(self):
        """
        Der Endpoint gibt TranscribeResponse mit 'formatted_message' zurueck.
        Kein direktes Senden im Python-Endpoint.
        """
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        # Arrange: mini FastAPI-App mit dem STT-Router
        app = FastAPI()

        # Patch alle externen Abhaengigkeiten
        mock_result = MagicMock()
        mock_result.text = "Test Transkript"
        mock_result.language = "de"
        mock_result.duration_seconds = 5.0

        with patch("backend.api.v1.stt._load_config", return_value={
            "stt": {"keep_audio": False, "audio_dir": "data/voice_messages", "max_duration_seconds": 900}
        }), patch("backend.stt.whisper_service.transcribe", new_callable=AsyncMock, return_value=mock_result), \
             patch("backend.api.v1.stt._summarize_transcript", return_value="Er fragt nach einem Meeting."), \
             patch("backend.api.v1.stt._save_to_chromadb"), \
             patch("backend.api.v1.stt._save_audio_file"):

            from backend.api.v1.stt import router
            app.include_router(router)
            client = TestClient(app)

            # Act: POST an /api/v1/stt/transcribe mit Multipart-Formular
            audio_bytes = b"\x00" * 100
            response = client.post(
                "/api/v1/stt/transcribe",
                data={
                    "chat_id": SARAH_CHAT_ID,
                    "chat_name": "Marie",
                    "sender": "Marie",
                    "timestamp": "1700000000",
                    "message_id": "test_msg_001",
                },
                files={"audio": ("voice.ogg", audio_bytes, "audio/ogg")},
            )

        # Assert: Response hat formatted_message, aber kein sendMessage-Aufruf
        assert response.status_code == 200
        body = response.json()
        assert "formatted_message" in body
        assert "status" in body
        # Der Endpoint sendet NICHT selbst — kein 'sent_to' oder 'whatsapp_sent' in der Antwort
        assert "sent_to" not in body
        assert "whatsapp_sent" not in body

    def test_stt_endpoint_formatted_message_contains_sender_and_chat(self):
        """formatted_message enthaelt Absender und Chat-Namen."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()

        mock_result = MagicMock()
        mock_result.text = "Ich bin unterwegs."
        mock_result.language = "de"
        mock_result.duration_seconds = 3.0

        with patch("backend.api.v1.stt._load_config", return_value={
            "stt": {"keep_audio": False, "audio_dir": "data/voice_messages", "max_duration_seconds": 900}
        }), patch("backend.stt.whisper_service.transcribe", new_callable=AsyncMock, return_value=mock_result), \
             patch("backend.api.v1.stt._summarize_transcript", return_value="Sie ist unterwegs."), \
             patch("backend.api.v1.stt._save_to_chromadb"), \
             patch("backend.api.v1.stt._save_audio_file"):

            from backend.api.v1.stt import router
            # Reset FastAPI app to avoid router re-registration conflicts
            app2 = FastAPI()
            from importlib import import_module
            stt_module = import_module("backend.api.v1.stt")
            app2.include_router(stt_module.router)
            client = TestClient(app2)

            response = client.post(
                "/api/v1/stt/transcribe",
                data={
                    "chat_id": SARAH_CHAT_ID,
                    "chat_name": "Familie",
                    "sender": "Marie",
                    "timestamp": "1700000000",
                    "message_id": "test_msg_002",
                },
                files={"audio": ("voice.ogg", b"\x00" * 100, "audio/ogg")},
            )

        assert response.status_code == 200
        body = response.json()
        fmt = body.get("formatted_message", "")
        assert "Marie" in fmt
        assert "Familie" in fmt

    def test_stt_endpoint_error_returns_error_status(self):
        """Bei Transkriptions-Fehler gibt der Endpoint status='error' zurueck (kein 500)."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()

        with patch("backend.api.v1.stt._load_config", return_value={
            "stt": {"keep_audio": False, "audio_dir": "data/voice_messages", "max_duration_seconds": 900}
        }), patch("backend.stt.whisper_service.transcribe",
                  new_callable=AsyncMock,
                  side_effect=RuntimeError("Kein Modell geladen")):

            from backend.api.v1.stt import router
            app3 = FastAPI()
            from importlib import import_module
            stt_module = import_module("backend.api.v1.stt")
            app3.include_router(stt_module.router)
            client = TestClient(app3)

            response = client.post(
                "/api/v1/stt/transcribe",
                data={
                    "chat_id": SARAH_CHAT_ID,
                    "chat_name": "TestChat",
                    "sender": "Jemand",
                    "timestamp": "1700000000",
                    "message_id": "test_msg_003",
                },
                files={"audio": ("voice.ogg", b"\x00" * 10, "audio/ogg")},
            )

        assert response.status_code == 200  # Fehler werden als 200 mit status='error' zurueckgegeben
        body = response.json()
        assert body["status"] == "error"
        assert "formatted_message" in body
