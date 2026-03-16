"""
test_acceptance_infra.py – Akzeptanztests fuer Infrastruktur

Abgedeckte Test-IDs:
  AT-INF-001  Health-Check Endpoint
  AT-INF-010  CORS erlaubt Frontend-Origin
  AT-INF-020  config.yaml wird geladen

Ausfuehren: pytest tests/test_acceptance_infra.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# conftest.py stub elasticsearch bevor main importiert wird
from backend.main import app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient mit eigener Test-DB."""
    import backend.db.database as db_module

    db_file = tmp_path / "test_infra.db"
    monkeypatch.setattr(db_module, "_db_path", db_file)

    import asyncio
    asyncio.get_event_loop().run_until_complete(db_module.init_db())

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# AT-INF-001: Health-Check Endpoint
# ---------------------------------------------------------------------------

def test_at_inf_001_health_returns_200(client):
    """AT-INF-001: GET /health gibt HTTP 200 zurueck."""
    response = client.get("/health")
    assert response.status_code == 200


def test_at_inf_001_health_returns_ok_status(client):
    """AT-INF-001: /health Response enthaelt status=ok."""
    response = client.get("/health")
    data = response.json()
    assert data.get("status") == "ok"


def test_at_inf_001_health_contains_app_info(client):
    """AT-INF-001: /health Response enthaelt App-Bezeichnung."""
    response = client.get("/health")
    data = response.json()
    assert "app" in data
    assert "version" in data


# ---------------------------------------------------------------------------
# AT-INF-010: CORS erlaubt Frontend-Origin
# ---------------------------------------------------------------------------

def test_at_inf_010_cors_middleware_configured():
    """
    AT-INF-010: Die CORS-Middleware ist in der App konfiguriert.

    Prueft die App-Konfiguration direkt, da FastAPI TestClient
    Middleware nicht im gleichen ASGI-Stack durchlaeuft wie ein
    echter HTTP-Client.
    """
    from starlette.middleware.cors import CORSMiddleware

    # Pruefe ob CORSMiddleware in der Middleware-Liste registriert ist
    middleware_classes = [
        m.cls for m in app.user_middleware
        if hasattr(m, "cls")
    ]
    assert CORSMiddleware in middleware_classes, (
        "CORSMiddleware ist nicht in der App registriert!"
    )


def test_at_inf_010_cors_allows_localhost_origins():
    """AT-INF-010: ALLOWED_ORIGINS enthaelt mindestens localhost-Eintraege."""
    from backend.main import ALLOWED_ORIGINS

    has_localhost = any("localhost" in origin for origin in ALLOWED_ORIGINS)
    assert has_localhost, (
        f"ALLOWED_ORIGINS enthaelt kein localhost: {ALLOWED_ORIGINS}"
    )


# ---------------------------------------------------------------------------
# AT-INF-020: config.yaml wird geladen
# ---------------------------------------------------------------------------

def test_at_inf_020_config_endpoint_returns_llm_config(client):
    """AT-INF-020: GET /api/config gibt llm-Konfiguration zurueck."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "llm" in data, f"Kein 'llm'-Key in Response: {data}"


def test_at_inf_020_config_no_api_key_in_response(client):
    """AT-INF-020: GET /api/config gibt KEINEN API-Key zurueck."""
    response = client.get("/api/config")
    data = response.json()
    llm = data.get("llm", {})
    assert "api_key" not in llm, (
        "API-Key darf NICHT in der Konfigurationsantwort enthalten sein!"
    )


def test_at_inf_020_config_loader_unit():
    """AT-INF-020: get_cfg() laedt config.yaml und gibt provider und paths zurueck."""
    from backend.llm.connector import get_cfg

    cfg = get_cfg()

    assert "llm" in cfg, "config.yaml muss 'llm'-Sektion enthalten"
    assert "provider" in cfg["llm"], "llm-Sektion muss 'provider' enthalten"
    assert "paths" in cfg, "config.yaml muss 'paths'-Sektion enthalten"
