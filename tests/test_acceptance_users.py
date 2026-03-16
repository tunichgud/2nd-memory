"""
test_acceptance_users.py – Akzeptanztests fuer /api/v1/users Endpunkte

Abgedeckte Test-IDs:
  AT-USR-001  User erstellen
  AT-USR-002  User auflisten
  AT-USR-003  User-Profil aktualisieren
  AT-USR-004  Leerer Display-Name wird abgelehnt
  AT-USR-005  Display-Name maximal 100 Zeichen
  AT-USR-006  Nicht existierender User gibt 404

Ausfuehren: pytest tests/test_acceptance_users.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# conftest.py stub elasticsearch bevor main importiert wird
from backend.main import app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """
    TestClient mit einer In-Memory-SQLite-Datenbank (tmp_path).
    Kein Leakage zwischen Tests.
    """
    import backend.db.database as db_module

    # Eigene DB-Datei pro Test
    db_file = tmp_path / "test_memosaur.db"
    monkeypatch.setattr(db_module, "_db_path", db_file)

    # DB initialisieren (Schema + Default-User)
    import asyncio
    asyncio.get_event_loop().run_until_complete(db_module.init_db())

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# AT-USR-001: User erstellen
# ---------------------------------------------------------------------------

def test_at_usr_001_create_user(client):
    """AT-USR-001: POST /api/v1/users mit gueltigem display_name gibt 201 zurueck."""
    # Arrange
    payload = {"display_name": "TestUser"}

    # Act
    response = client.post("/api/v1/users", json=payload)

    # Assert
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["display_name"] == "TestUser"
    assert "id" in data
    assert "created_at" in data


def test_at_usr_001_user_retrievable_after_create(client):
    """AT-USR-001: Nach dem Erstellen ist der User via GET abrufbar."""
    # Arrange
    response = client.post("/api/v1/users", json={"display_name": "Abrufbarer User"})
    assert response.status_code == 201
    user_id = response.json()["id"]

    # Act
    get_response = client.get(f"/api/v1/users/{user_id}")

    # Assert
    assert get_response.status_code == 200
    assert get_response.json()["id"] == user_id
    assert get_response.json()["display_name"] == "Abrufbarer User"


# ---------------------------------------------------------------------------
# AT-USR-002: User auflisten
# ---------------------------------------------------------------------------

def test_at_usr_002_list_users(client):
    """AT-USR-002: GET /api/v1/users gibt alle User zurueck."""
    # Arrange: 2 zusaetzliche User anlegen (Default-User existiert bereits)
    client.post("/api/v1/users", json={"display_name": "User Eins"})
    client.post("/api/v1/users", json={"display_name": "User Zwei"})

    # Act
    response = client.get("/api/v1/users")

    # Assert
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    names = [u["display_name"] for u in users]
    assert "User Eins" in names
    assert "User Zwei" in names


def test_at_usr_002_list_returns_list(client):
    """AT-USR-002: Antwort ist immer eine Liste (auch wenn leer)."""
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# AT-USR-003: User-Profil aktualisieren
# ---------------------------------------------------------------------------

def test_at_usr_003_update_profile(client):
    """AT-USR-003: PATCH /api/v1/users/{id} aktualisiert display_name."""
    # Arrange
    create = client.post("/api/v1/users", json={"display_name": "Alter Name"})
    user_id = create.json()["id"]

    # Act
    response = client.patch(f"/api/v1/users/{user_id}", json={"display_name": "Neuer Name"})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Neuer Name"
    assert data["id"] == user_id


def test_at_usr_003_update_reflected_in_get(client):
    """AT-USR-003: Aktualisierter Name ist anschliessend via GET sichtbar."""
    create = client.post("/api/v1/users", json={"display_name": "Vorher"})
    user_id = create.json()["id"]

    client.patch(f"/api/v1/users/{user_id}", json={"display_name": "Nachher"})

    get_response = client.get(f"/api/v1/users/{user_id}")
    assert get_response.json()["display_name"] == "Nachher"


# ---------------------------------------------------------------------------
# AT-USR-004: Leerer Display-Name wird abgelehnt
# ---------------------------------------------------------------------------

def test_at_usr_004_empty_name_rejected(client):
    """AT-USR-004: Leerer display_name gibt 400 zurueck."""
    # Arrange
    create = client.post("/api/v1/users", json={"display_name": "Valider User"})
    user_id = create.json()["id"]

    # Act
    response = client.patch(f"/api/v1/users/{user_id}", json={"display_name": ""})

    # Assert
    assert response.status_code == 400, f"Erwartet 400, bekam {response.status_code}: {response.text}"


def test_at_usr_004_whitespace_only_name_rejected(client):
    """AT-USR-004: Nur-Leerzeichen display_name gibt 400 zurueck."""
    create = client.post("/api/v1/users", json={"display_name": "Valider User"})
    user_id = create.json()["id"]

    response = client.patch(f"/api/v1/users/{user_id}", json={"display_name": "   "})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AT-USR-005: Display-Name maximal 100 Zeichen
# ---------------------------------------------------------------------------

def test_at_usr_005_name_too_long_rejected(client):
    """AT-USR-005: display_name mit 101 Zeichen gibt 400 zurueck."""
    create = client.post("/api/v1/users", json={"display_name": "Valider User"})
    user_id = create.json()["id"]

    long_name = "A" * 101
    response = client.patch(f"/api/v1/users/{user_id}", json={"display_name": long_name})

    assert response.status_code == 400, f"Erwartet 400, bekam {response.status_code}"


def test_at_usr_005_name_exactly_100_accepted(client):
    """AT-USR-005: display_name mit genau 100 Zeichen wird akzeptiert."""
    create = client.post("/api/v1/users", json={"display_name": "Valider User"})
    user_id = create.json()["id"]

    name_100 = "B" * 100
    response = client.patch(f"/api/v1/users/{user_id}", json={"display_name": name_100})

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AT-USR-006: Nicht existierender User gibt 404
# ---------------------------------------------------------------------------

def test_at_usr_006_nonexistent_user_get_404(client):
    """AT-USR-006: GET fuer nicht existierende User-ID gibt 404 zurueck."""
    response = client.get("/api/v1/users/nonexistent-id-12345")
    assert response.status_code == 404


def test_at_usr_006_nonexistent_user_patch_404(client):
    """AT-USR-006: PATCH fuer nicht existierende User-ID gibt 404 zurueck."""
    response = client.patch(
        "/api/v1/users/nonexistent-id-12345",
        json={"display_name": "Neuer Name"},
    )
    assert response.status_code == 404
