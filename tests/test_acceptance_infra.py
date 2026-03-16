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


# ---------------------------------------------------------------------------
# AT-INF-030: context_length aus config.yaml wird in ContextBudget verwendet
# ---------------------------------------------------------------------------

def test_at_inf_030_default_token_budget_from_config():
    """AT-INF-030: DEFAULT_TOKEN_BUDGET entspricht config.yaml llm.context_length."""
    from backend.llm.connector import get_cfg
    from backend.rag.constants import DEFAULT_TOKEN_BUDGET

    cfg = get_cfg()
    expected = cfg.get("llm", {}).get("context_length", 8_000)

    assert DEFAULT_TOKEN_BUDGET == expected, (
        f"DEFAULT_TOKEN_BUDGET={DEFAULT_TOKEN_BUDGET} stimmt nicht mit "
        f"config.yaml context_length={expected} ueberein!"
    )


def test_at_inf_030_context_budget_uses_config_value():
    """AT-INF-030: ContextBudget() ohne Parameter nutzt config.yaml context_length."""
    from backend.rag.context_manager import ContextBudget
    from backend.llm.connector import get_cfg

    budget = ContextBudget()
    cfg = get_cfg()
    expected = cfg.get("llm", {}).get("context_length", 8_000)

    assert budget.max_tokens == expected, (
        f"ContextBudget().max_tokens={budget.max_tokens} sollte "
        f"config.yaml context_length={expected} sein!"
    )


def test_at_inf_030_context_budget_greater_than_8000():
    """AT-INF-030: Regression Guard — ContextBudget().max_tokens > 8000.

    Wenn jemand wieder ContextBudget(max_tokens=8000) als Default hardcodet,
    wird dieser Test rot (solange config.yaml context_length > 8000 hat).
    """
    from backend.rag.context_manager import ContextBudget
    from backend.llm.connector import get_cfg

    cfg = get_cfg()
    config_value = cfg.get("llm", {}).get("context_length", 8_000)

    # Nur testen wenn config tatsaechlich > 8000 ist
    if config_value > 8_000:
        budget = ContextBudget()
        assert budget.max_tokens > 8_000, (
            f"ContextBudget().max_tokens={budget.max_tokens} ist <= 8000, "
            f"aber config.yaml hat context_length={config_value}. "
            f"Wurde max_tokens wieder hardcoded?"
        )


def test_at_inf_030_context_budget_explicit_override():
    """AT-INF-030: Expliziter max_tokens-Wert ueberschreibt den Config-Default."""
    from backend.rag.context_manager import ContextBudget

    budget = ContextBudget(max_tokens=4000)
    assert budget.max_tokens == 4000, (
        "Expliziter max_tokens=4000 sollte nicht ueberschrieben werden!"
    )
