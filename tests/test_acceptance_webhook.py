"""
test_acceptance_webhook.py – Akzeptanztests fuer den WhatsApp Webhook

Abgedeckte Test-IDs:
  AT-RAG-040  Webhook verarbeitet eingehende Nachrichten
  AT-RAG-041  Bot-Nachrichten werden nicht beantwortet
  AT-RAG-042  Ausgehende Nachrichten werden nicht beantwortet

Ausfuehren: pytest tests/test_acceptance_webhook.py -v
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# conftest.py stub elasticsearch bevor main importiert wird
from backend.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient mit eigener Test-DB und gemockten LLM-Abhaengigkeiten."""
    import backend.db.database as db_module

    db_file = tmp_path / "test_webhook.db"
    monkeypatch.setattr(db_module, "_db_path", db_file)

    import asyncio
    asyncio.get_event_loop().run_until_complete(db_module.init_db())

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_rag_dependencies(monkeypatch):
    """
    Mockt alle LLM/ChromaDB-Abhaengigkeiten des Webhooks.
    Kein echter API-Call, keine echte Vektordatenbank.
    """
    # Mock embed_single
    monkeypatch.setattr(
        "backend.rag.embedder.embed_single",
        lambda text: [0.1] * 384,
    )
    # Mock upsert_documents_v2
    monkeypatch.setattr(
        "backend.rag.store_v2.upsert_documents_v2",
        lambda *args, **kwargs: None,
    )
    # Mock answer_v2 (RAG-Pipeline)
    monkeypatch.setattr(
        "backend.rag.retriever_v2.answer_v2",
        lambda **kwargs: {"answer": "Test-Antwort vom Mock-LLM", "query_id": "mock-query-id"},
    )


# ---------------------------------------------------------------------------
# AT-RAG-040: Webhook verarbeitet eingehende Nachrichten
# ---------------------------------------------------------------------------

def test_at_rag_040_webhook_processes_incoming_message(client):
    """AT-RAG-040: POST /api/v1/webhook mit is_incoming=true gibt status=success zurueck."""
    # Arrange
    payload = {
        "sender": "Ich",
        "text": "Wann war ich in Rom?",
        "is_incoming": True,
    }

    # Act
    response = client.post("/api/v1/webhook", json=payload)

    # Assert
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "success"


def test_at_rag_040_webhook_returns_answer_for_incoming(client):
    """AT-RAG-040: Eingehende Nachricht erzeugt eine LLM-Antwort im 'answer'-Feld."""
    payload = {
        "sender": "Ich",
        "text": "Was habe ich letzten Dienstag gemacht?",
        "is_incoming": True,
    }

    response = client.post("/api/v1/webhook", json=payload)
    data = response.json()

    assert data["status"] == "success"
    assert data.get("answer") is not None, (
        "Eingehende Nachricht muss eine Antwort im 'answer'-Feld haben"
    )


# ---------------------------------------------------------------------------
# AT-RAG-041: Bot-Nachrichten werden nicht beantwortet
# ---------------------------------------------------------------------------

def test_at_rag_041_bot_message_not_answered(client):
    """AT-RAG-041: Nachricht mit Dino-Prefix wird nicht beantwortet (answer=null)."""
    payload = {
        "sender": "KI (Memosaur)",
        "text": "🦕 Das ist eine Antwort vom Bot",
        "is_incoming": True,
    }

    response = client.post("/api/v1/webhook", json=payload)
    data = response.json()

    assert data["status"] == "success"
    assert data.get("answer") is None, (
        f"Bot-Nachricht (Dino-Prefix) darf KEINE Antwort erhalten, "
        f"bekam: {data.get('answer')}"
    )


def test_at_rag_041_bot_message_indexed(client, monkeypatch):
    """AT-RAG-041: Bot-Nachricht wird trotzdem in ChromaDB indexiert."""
    indexed_docs = []

    def _capture_upsert(collection, ids, documents, embeddings, metadatas):
        indexed_docs.append({
            "collection": collection,
            "documents": documents,
            "metadatas": metadatas,
        })

    monkeypatch.setattr(
        "backend.rag.store_v2.upsert_documents_v2",
        _capture_upsert,
    )

    payload = {
        "sender": "KI (Memosaur)",
        "text": "🦕 Test-Antwort",
        "is_incoming": True,
    }

    client.post("/api/v1/webhook", json=payload)

    # Muss mindestens einen Indexierungs-Aufruf gegeben haben
    assert len(indexed_docs) > 0, (
        "Bot-Nachricht muss in ChromaDB indexiert werden"
    )


# ---------------------------------------------------------------------------
# AT-RAG-042: Ausgehende Nachrichten werden nicht beantwortet
# ---------------------------------------------------------------------------

def test_at_rag_042_outgoing_message_not_answered(client):
    """AT-RAG-042: Ausgehende Nachricht (is_incoming=false) bekommt answer=null."""
    payload = {
        "sender": "Ich",
        "text": "Wir treffen uns morgen",
        "is_incoming": False,
    }

    response = client.post("/api/v1/webhook", json=payload)
    data = response.json()

    assert data["status"] == "success"
    assert data.get("answer") is None, (
        f"Ausgehende Nachricht darf KEINE Antwort erhalten, "
        f"bekam: {data.get('answer')}"
    )


def test_at_rag_042_outgoing_message_indexed(client, monkeypatch):
    """AT-RAG-042: Ausgehende Nachricht wird trotzdem in ChromaDB indexiert."""
    indexed_docs = []

    def _capture_upsert(collection, ids, documents, embeddings, metadatas):
        indexed_docs.append({
            "collection": collection,
            "documents": documents,
        })

    monkeypatch.setattr(
        "backend.rag.store_v2.upsert_documents_v2",
        _capture_upsert,
    )

    payload = {
        "sender": "Ich",
        "text": "Ausgehende Test-Nachricht",
        "is_incoming": False,
    }

    client.post("/api/v1/webhook", json=payload)

    assert len(indexed_docs) > 0, (
        "Ausgehende Nachricht muss in ChromaDB indexiert werden"
    )
