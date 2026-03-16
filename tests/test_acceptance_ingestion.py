"""
test_acceptance_ingestion.py – Akzeptanztests fuer Daten-Ingestion

Abgedeckte Test-IDs:
  AT-ING-001  WhatsApp TXT-Datei (Android-Format) erfolgreich importieren
  AT-ING-002  iOS-Format wird erkannt
  AT-ING-003  System-Messages werden gefiltert
  AT-ING-004  Mehrzeilige Nachrichten werden zusammengefuegt
  AT-ING-041  User muss existieren (Reviews)
  AT-ING-060  Status gibt Dokumentzaehler pro Collection
  AT-ING-061  Leerer User gibt Nullen zurueck

Ausfuehren: pytest tests/test_acceptance_ingestion.py -v
"""
from __future__ import annotations

import io
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# conftest.py stub elasticsearch bevor main importiert wird
from backend.main import app  # noqa: E402
from backend.ingestion.whatsapp import parse_whatsapp_export


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient mit eigener Test-DB."""
    import backend.db.database as db_module

    db_file = tmp_path / "test_ingestion.db"
    monkeypatch.setattr(db_module, "_db_path", db_file)

    import asyncio
    asyncio.get_event_loop().run_until_complete(db_module.init_db())

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# AT-ING-001: WhatsApp TXT-Datei (Android-Format) parsen
# ---------------------------------------------------------------------------

def test_at_ing_001_android_format_parsed(tmp_path):
    """AT-ING-001: Android-Format wird korrekt geparst."""
    # Arrange
    content = (
        "01.01.2025, 12:00 - Alice: Hallo!\n"
        "01.01.2025, 12:01 - Bob: Hey, wie geht's?\n"
        "01.01.2025, 12:02 - Alice: Gut, danke.\n"
    )
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    # Act
    messages = parse_whatsapp_export(chat_file)

    # Assert
    assert len(messages) == 3
    assert messages[0]["sender"] == "Alice"
    assert messages[0]["content"] == "Hallo!"
    assert messages[1]["sender"] == "Bob"


def test_at_ing_001_android_format_date_parsed(tmp_path):
    """AT-ING-001: Datum wird aus Android-Format korrekt geparst."""
    content = "01.01.2025, 12:00 - Alice: Test\n"
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    messages = parse_whatsapp_export(chat_file)

    assert len(messages) == 1
    assert messages[0]["date_ts"] > 0, "Timestamp muss geparst werden"
    assert "01.01.2025" in messages[0]["date_str"]


# ---------------------------------------------------------------------------
# AT-ING-002: iOS-Format wird erkannt
# ---------------------------------------------------------------------------

def test_at_ing_002_ios_format_parsed(tmp_path):
    """AT-ING-002: iOS-Format [DD.MM.YYYY, HH:MM:SS] wird geparst."""
    # Arrange
    content = (
        "[01.01.2025, 12:00:00] Alice: Guten Morgen!\n"
        "[01.01.2025, 12:01:30] Bob: Morgen!\n"
    )
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    # Act
    messages = parse_whatsapp_export(chat_file)

    # Assert
    assert len(messages) == 2
    assert messages[0]["sender"] == "Alice"
    assert messages[0]["content"] == "Guten Morgen!"
    assert messages[1]["sender"] == "Bob"


def test_at_ing_002_ios_format_timestamp(tmp_path):
    """AT-ING-002: iOS-Format gibt validen Timestamp zurueck."""
    content = "[15.03.2025, 09:30:00] Sarah: Test\n"
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    messages = parse_whatsapp_export(chat_file)

    assert messages[0]["date_ts"] > 0


# ---------------------------------------------------------------------------
# AT-ING-003: System-Messages werden gefiltert
# ---------------------------------------------------------------------------

def test_at_ing_003_media_omitted_filtered(tmp_path):
    """AT-ING-003: '<Medien weggelassen>' wird NICHT in ChromaDB indexiert."""
    # Arrange
    content = (
        "01.01.2025, 12:00 - Alice: Hallo!\n"
        "01.01.2025, 12:01 - Alice: <Medien weggelassen>\n"
        "01.01.2025, 12:02 - Bob: Ja!\n"
    )
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    # Act
    messages = parse_whatsapp_export(chat_file)

    # Assert: nur echte Nachrichten, keine System-Messages
    assert len(messages) == 2
    contents = [m["content"] for m in messages]
    assert "<Medien weggelassen>" not in contents
    assert "Hallo!" in contents
    assert "Ja!" in contents


def test_at_ing_003_media_omitted_english_filtered(tmp_path):
    """AT-ING-003: '<Media omitted>' (englisch) wird ebenfalls gefiltert."""
    content = (
        "01.01.2025, 12:00 - Alice: Hello!\n"
        "01.01.2025, 12:01 - Alice: <Media omitted>\n"
    )
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    messages = parse_whatsapp_export(chat_file)

    assert len(messages) == 1
    assert messages[0]["content"] == "Hello!"


def test_at_ing_003_encryption_notice_filtered(tmp_path):
    """AT-ING-003: Verschluesselungs-Hinweis wird gefiltert."""
    content = (
        "01.01.2025, 12:00 - Alice: Echter Text\n"
        "01.01.2025, 12:01 - System: Nachrichten und Anrufe sind Ende-zu-Ende-verschlüsselt\n"
    )
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    messages = parse_whatsapp_export(chat_file)

    # Der Verschluesselungs-Hinweis soll nicht als Nachricht gewertet werden
    contents = [m["content"] for m in messages]
    assert not any(
        "Ende-zu-Ende" in c for c in contents
    ), f"Systemhinweis soll gefiltert werden, aber enthalten: {contents}"


# ---------------------------------------------------------------------------
# AT-ING-004: Mehrzeilige Nachrichten werden zusammengefuegt
# ---------------------------------------------------------------------------

def test_at_ing_004_multiline_message_merged(tmp_path):
    """AT-ING-004: Mehrzeilige Nachricht wird zu einer Nachricht zusammengefuegt."""
    # Arrange
    content = (
        "01.01.2025, 12:00 - Alice: Erste Zeile\n"
        "Zweite Zeile\n"
        "Dritte Zeile\n"
        "01.01.2025, 12:01 - Bob: Neue Nachricht\n"
    )
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    # Act
    messages = parse_whatsapp_export(chat_file)

    # Assert
    assert len(messages) == 2, (
        f"Erwartet 2 Nachrichten (Fortsetzungszeilen zusammengefuegt), "
        f"bekam {len(messages)}: {messages}"
    )
    # Die erste Nachricht soll alle drei Zeilen enthalten
    assert "Erste Zeile" in messages[0]["content"]
    assert "Zweite Zeile" in messages[0]["content"]
    assert "Dritte Zeile" in messages[0]["content"]


def test_at_ing_004_single_line_unchanged(tmp_path):
    """AT-ING-004: Einzeilige Nachricht bleibt unveraendert."""
    content = "01.01.2025, 12:00 - Alice: Einzel-Nachricht\n"
    chat_file = tmp_path / "_chat.txt"
    chat_file.write_text(content, encoding="utf-8")

    messages = parse_whatsapp_export(chat_file)

    assert len(messages) == 1
    assert messages[0]["content"] == "Einzel-Nachricht"


# ---------------------------------------------------------------------------
# AT-ING-041: User muss existieren (Reviews)
# ---------------------------------------------------------------------------

def test_at_ing_041_reviews_unknown_user_gives_404(client):
    """AT-ING-041: POST /api/v1/ingest/reviews mit nicht existierender user_id gibt 404."""
    # Act
    response = client.post("/api/v1/ingest/reviews?user_id=fake_user_xyz_12345")

    # Assert
    assert response.status_code == 404, (
        f"Erwartet 404 fuer nicht existierenden User, bekam {response.status_code}: {response.text}"
    )


def test_at_ing_041_saved_unknown_user_gives_404(client):
    """AT-ING-041: POST /api/v1/ingest/saved mit nicht existierender user_id gibt 404."""
    response = client.post("/api/v1/ingest/saved?user_id=fake_user_xyz_12345")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# AT-ING-060: Status gibt Dokumentzaehler pro Collection
# AT-ING-061: Leerer User gibt Nullen zurueck
# ---------------------------------------------------------------------------

def test_at_ing_060_status_endpoint_returns_all_collections(client, monkeypatch):
    """AT-ING-060: GET /api/v1/ingest/status gibt alle vier Collections zurueck."""
    # Mock count_documents_for_user um ChromaDB nicht benoetigen
    import backend.api.v1.ingest as ingest_module

    def _mock_count(collection: str, user_id: str) -> int:
        counts = {
            "messages": 50,
            "photos": 10,
            "reviews": 5,
            "saved_places": 3,
        }
        return counts.get(collection, 0)

    monkeypatch.setattr(
        "backend.rag.store_v2.count_documents_for_user",
        _mock_count,
    )

    # Benutze den Default-User
    from backend.db.database import DEFAULT_USER_ID
    response = client.get(f"/api/v1/ingest/status?user_id={DEFAULT_USER_ID}")

    assert response.status_code == 200, response.text
    data = response.json()

    assert "messages" in data
    assert "photos" in data
    assert "reviews" in data
    assert "saved_places" in data

    assert data["messages"] == 50
    assert data["photos"] == 10
    assert data["reviews"] == 5
    assert data["saved_places"] == 3


def test_at_ing_061_empty_user_gives_zeros(client, monkeypatch):
    """AT-ING-061: Status fuer User ohne Daten gibt ueberall 0 zurueck."""
    import backend.api.v1.ingest as ingest_module

    monkeypatch.setattr(
        "backend.rag.store_v2.count_documents_for_user",
        lambda collection, user_id: 0,
    )

    # Eigenen User anlegen
    create = client.post("/api/v1/users", json={"display_name": "LeererUser"})
    user_id = create.json()["id"]

    response = client.get(f"/api/v1/ingest/status?user_id={user_id}")

    assert response.status_code == 200
    data = response.json()
    assert all(v == 0 for v in data.values()), (
        f"Alle Werte sollen 0 sein fuer leeren User, bekam: {data}"
    )
