"""
test_users.py – Tests für /api/v1/users Endpunkte (inkl. Profil-Bearbeitung)
"""

import pytest
from httpx import AsyncClient
from backend.main import app


@pytest.mark.asyncio
async def test_create_user():
    """Test: User erstellen"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/users", json={"display_name": "Test User"})
        assert response.status_code == 201
        data = response.json()
        assert data["display_name"] == "Test User"
        assert "id" in data
        assert "created_at" in data


@pytest.mark.asyncio
async def test_list_users():
    """Test: User-Liste abrufen"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user first
        await ac.post("/api/v1/users", json={"display_name": "User 1"})
        await ac.post("/api/v1/users", json={"display_name": "User 2"})

        # List users
        response = await ac.get("/api/v1/users")
        assert response.status_code == 200
        users = response.json()
        assert len(users) >= 2


@pytest.mark.asyncio
async def test_get_user():
    """Test: Einzelnen User abrufen"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        create_response = await ac.post("/api/v1/users", json={"display_name": "Test User"})
        user_id = create_response.json()["id"]

        # Get user
        response = await ac.get(f"/api/v1/users/{user_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id
        assert data["display_name"] == "Test User"


@pytest.mark.asyncio
async def test_get_nonexistent_user():
    """Test: Nicht-existierenden User abrufen (sollte 404 zurückgeben)"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/users/invalid-id-12345")
        assert response.status_code == 404
        assert "nicht gefunden" in response.json()["detail"].lower()


# -------------------------------------------------------------------------
# Profil-Bearbeitung Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_user_profile():
    """Test: Display name erfolgreich ändern"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        response = await ac.post("/api/v1/users", json={"display_name": "Original Name"})
        user_id = response.json()["id"]

        # Update name
        response = await ac.patch(
            f"/api/v1/users/{user_id}",
            json={"display_name": "Updated Name"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"
        assert data["id"] == user_id


@pytest.mark.asyncio
async def test_update_user_profile_empty_name():
    """Test: Leeren Namen ablehnen (400 Bad Request)"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        response = await ac.post("/api/v1/users", json={"display_name": "Test User"})
        user_id = response.json()["id"]

        # Try to update with empty name
        response = await ac.patch(
            f"/api/v1/users/{user_id}",
            json={"display_name": ""}
        )
        assert response.status_code == 400
        assert "leer" in response.json()["detail"].lower()

        # Try with whitespace-only name
        response = await ac.patch(
            f"/api/v1/users/{user_id}",
            json={"display_name": "   "}
        )
        assert response.status_code == 400
        assert "leer" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_user_profile_too_long():
    """Test: Namen mit > 100 Zeichen ablehnen (400 Bad Request)"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        response = await ac.post("/api/v1/users", json={"display_name": "Test User"})
        user_id = response.json()["id"]

        # Try to update with name > 100 chars
        long_name = "A" * 101
        response = await ac.patch(
            f"/api/v1/users/{user_id}",
            json={"display_name": long_name}
        )
        assert response.status_code == 400
        assert "100" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_user_profile_trim_whitespace():
    """Test: Whitespace am Anfang/Ende wird entfernt"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        response = await ac.post("/api/v1/users", json={"display_name": "Test User"})
        user_id = response.json()["id"]

        # Update with padded name
        response = await ac.patch(
            f"/api/v1/users/{user_id}",
            json={"display_name": "  Trimmed Name  "}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Trimmed Name"  # Whitespace removed


@pytest.mark.asyncio
async def test_update_nonexistent_user():
    """Test: Nicht-existierenden User aktualisieren (404)"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.patch(
            "/api/v1/users/nonexistent-id",
            json={"display_name": "New Name"}
        )
        assert response.status_code == 404
        assert "nicht gefunden" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_user_profile_unicode():
    """Test: Unicode-Namen (Emojis, Umlaute) erlaubt"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        response = await ac.post("/api/v1/users", json={"display_name": "Test User"})
        user_id = response.json()["id"]

        # Update with unicode name
        unicode_name = "Max Müller 🚀🇩🇪"
        response = await ac.patch(
            f"/api/v1/users/{user_id}",
            json={"display_name": unicode_name}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == unicode_name


@pytest.mark.asyncio
async def test_update_user_profile_special_chars():
    """Test: Sonderzeichen in Namen erlaubt"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        response = await ac.post("/api/v1/users", json={"display_name": "Test User"})
        user_id = response.json()["id"]

        # Update with special chars
        special_name = "O'Connor-Smith (Jr.)"
        response = await ac.patch(
            f"/api/v1/users/{user_id}",
            json={"display_name": special_name}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == special_name
