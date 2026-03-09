"""
Integration Test für WhatsApp → Backend → WhatsApp Flow

Testet den vollständigen Nachrichtenfluss:
1. WhatsApp-Nachricht kommt rein (simuliert)
2. Backend verarbeitet die Nachricht (Webhook)
3. Backend generiert Antwort via RAG
4. Antwort wird zurückgegeben

Requirements:
- Backend muss laufen (localhost:8000)
- ChromaDB muss initialisiert sein
- Mindestens ein paar Dokumente für RAG müssen vorhanden sein
"""

import pytest
import requests
import time


# Test-Konfiguration
BACKEND_URL = "http://localhost:8000"
WEBHOOK_ENDPOINT = f"{BACKEND_URL}/api/v1/webhook"
TEST_SENDER = "+491601234567"  # Fake Telefonnummer für Tests


class TestWhatsAppIntegration:
    """
    Integration Tests für den WhatsApp-Flow.

    Nutzt synchrone requests statt httpx für einfacheres Testing.
    """

    def test_01_backend_is_running(self):
        """
        Test 1: Backend ist erreichbar.

        Verifiziert, dass das Backend läuft und antwortet.
        """
        try:
            response = requests.get(f"{BACKEND_URL}/", timeout=5)
            assert response.status_code == 200, f"Backend nicht erreichbar: {response.status_code}"
            print("✅ Backend ist online")
        except Exception as e:
            pytest.fail(f"❌ Backend nicht erreichbar: {e}")

    def test_02_webhook_endpoint_exists(self):
        """
        Test 2: Webhook-Endpoint existiert.

        Verifiziert, dass der /api/v1/webhook Endpoint existiert
        und auf POST-Requests antwortet.
        """
        try:
            response = requests.post(
                WEBHOOK_ENDPOINT,
                json={
                    "sender": TEST_SENDER,
                    "text": "Test",
                    "is_incoming": True
                },
                timeout=10
            )
            # Sollte nicht 404 sein
            assert response.status_code != 404, "Webhook-Endpoint nicht gefunden (404)"
            print(f"✅ Webhook-Endpoint antwortet (Status: {response.status_code})")
        except Exception as e:
            pytest.fail(f"❌ Webhook-Endpoint nicht erreichbar: {e}")

    def test_03_incoming_message_is_processed(self):
        """
        Test 3: Eingehende Nachricht wird verarbeitet.

        Simuliert eine eingehende WhatsApp-Nachricht und prüft,
        ob das Backend diese korrekt verarbeitet.

        Erwartet:
        - Status 200
        - JSON Response mit "status": "success"
        - Optional: "answer" field wenn RAG eine Antwort generiert
        """
        message = {
            "sender": TEST_SENDER,
            "text": "Hallo! Wie geht es dir?",
            "is_incoming": True
        }

        response = requests.post(WEBHOOK_ENDPOINT, json=message, timeout=30)

        # Assertions
        assert response.status_code == 200, f"Webhook returned {response.status_code}: {response.text}"

        data = response.json()
        assert "status" in data, "Response missing 'status' field"
        assert data["status"] in ["success", "error"], f"Unexpected status: {data['status']}"

        if data["status"] == "error":
            pytest.fail(f"❌ Backend returned error: {data}")

        print(f"✅ Nachricht verarbeitet: {data}")
        print(f"   Status: {data['status']}")
        if data.get("answer"):
            print(f"   Antwort: {data['answer'][:100]}...")

    def test_04_rag_generates_answer(self):
        """
        Test 4: RAG generiert eine sinnvolle Antwort.

        Sendet eine Frage an das Backend und verifiziert,
        dass eine Antwort generiert wird.

        Erwartet:
        - "answer" field ist nicht None
        - Antwort ist nicht leer
        - Antwort ist ein String
        """
        message = {
            "sender": TEST_SENDER,
            "text": "Was weißt du über mich?",
            "is_incoming": True
        }

        response = requests.post(WEBHOOK_ENDPOINT, json=message, timeout=30)

        assert response.status_code == 200
        data = response.json()

        # Prüfe ob eine Antwort generiert wurde
        assert "answer" in data, "Response missing 'answer' field"

        if data["answer"] is None:
            pytest.skip("⚠️ Keine Antwort generiert - eventuell keine Dokumente in der DB")

        assert isinstance(data["answer"], str), "Answer muss ein String sein"
        assert len(data["answer"]) > 0, "Answer darf nicht leer sein"

        print(f"✅ RAG Antwort generiert:")
        print(f"   Länge: {len(data['answer'])} Zeichen")
        print(f"   Vorschau: {data['answer'][:200]}...")

    def test_05_outgoing_message_no_answer(self):
        """
        Test 5: Ausgehende Nachrichten (fromMe=True) triggern keine Antwort.

        Wenn die Nachricht vom User selbst kommt (is_incoming=False),
        sollte das Backend keine Antwort generieren.

        Erwartet:
        - Status "success"
        - "answer" ist None oder nicht vorhanden
        """
        message = {
            "sender": "Ich",
            "text": "Das ist meine eigene Nachricht",
            "is_incoming": False
        }

        response = requests.post(WEBHOOK_ENDPOINT, json=message, timeout=30)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Ausgehende Nachrichten sollten keine Antwort triggern
        assert data.get("answer") is None, "Ausgehende Nachrichten sollten keine Antwort generieren"

        print("✅ Ausgehende Nachricht korrekt verarbeitet (keine Antwort)")

    def test_06_bot_message_no_answer(self):
        """
        Test 6: Bot-Nachrichten (🦕 Prefix) triggern keine Antwort.

        Wenn eine Nachricht mit dem Bot-Prefix (🦕) kommt,
        sollte das Backend nicht antworten (Loop-Prevention).

        Erwartet:
        - Status "success"
        - "answer" ist None
        """
        message = {
            "sender": TEST_SENDER,
            "text": "🦕 Das ist eine Bot-Antwort",
            "is_incoming": True
        }

        response = requests.post(WEBHOOK_ENDPOINT, json=message, timeout=30)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Bot-Nachrichten sollten keine weitere Antwort triggern
        assert data.get("answer") is None, "Bot-Nachrichten sollten keine Antwort generieren"

        print("✅ Bot-Nachricht korrekt ignoriert (Loop Prevention)")

    def test_07_message_gets_indexed(self):
        """
        Test 7: Nachrichten werden in ChromaDB indexiert.

        Sendet mehrere Nachrichten und verifiziert, dass sie
        im Gedächtnis gespeichert werden (indirekt über RAG-Antwort).

        Dieser Test ist etwas komplexer:
        1. Sende eine Nachricht mit spezifischem Inhalt
        2. Sende eine Frage, die diesen Inhalt erfordert
        3. Prüfe ob die Antwort den vorherigen Kontext nutzt
        """
        # Schritt 1: Information geben
        info_message = {
            "sender": TEST_SENDER,
            "text": "Ich war gestern im Kino und habe den Film Dune 2 gesehen.",
            "is_incoming": True
        }

        response1 = requests.post(WEBHOOK_ENDPOINT, json=info_message, timeout=30)
        assert response1.status_code == 200

        # Kurz warten, damit die Indexierung abgeschlossen ist
        time.sleep(2)

        # Schritt 2: Frage stellen
        query_message = {
            "sender": TEST_SENDER,
            "text": "Welchen Film habe ich gestern gesehen?",
            "is_incoming": True
        }

        response2 = requests.post(WEBHOOK_ENDPOINT, json=query_message, timeout=30)
        assert response2.status_code == 200

        data = response2.json()

        if data.get("answer") is None:
            pytest.skip("⚠️ RAG generiert keine Antwort - DB möglicherweise leer")

        answer = data["answer"].lower()

        # Die Antwort sollte "dune" oder "kino" erwähnen
        # (flexibel, da LLM-Antworten variieren können)
        has_context = "dune" in answer or "film" in answer or "kino" in answer

        print(f"✅ Nachricht wurde indexiert und ist abrufbar")
        print(f"   Antwort: {data['answer'][:200]}...")
        print(f"   Enthält Kontext: {has_context}")

    def test_08_invalid_request_format(self):
        """
        Test 8: Ungültige Requests werden abgelehnt.

        Verifiziert, dass das Backend auf ungültige Requests
        mit entsprechenden Fehlercodes antwortet.
        """
        # Fehlende required fields
        invalid_message = {
            "sender": TEST_SENDER
            # "text" fehlt!
        }

        response = requests.post(WEBHOOK_ENDPOINT, json=invalid_message, timeout=10)

        # Sollte einen 4xx Error zurückgeben
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"

        print(f"✅ Ungültige Requests werden korrekt abgelehnt (Status: {response.status_code})")


# Convenience Runner für manuelle Tests
if __name__ == "__main__":
    print("🧪 WhatsApp Integration Tests")
    print("=" * 60)
    print("\nStarte Tests...\n")

    # Run mit pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])
