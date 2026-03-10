"""
main.py – FastAPI Hauptanwendung für memosaur.

v0-Endpunkte (/api/*) bleiben erhalten (Rückwärtskompatibilität).
v1-Endpunkte (/api/v1/*) sind token-aware und user-scoped.

Start: python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ⚠️  WICHTIG: .env laden BEVOR andere Module importiert werden!
# Sonst sind ENV-Variablen in oauth.py, connector.py etc. nicht verfügbar
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(BASE_DIR))

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="memosaur",
    description="Persönliches Gedächtnis-System – Privacy-First RAG",
    version="2.0.0",
)

# CORS Configuration (Security Fix)
# ENV: CORS_ORIGINS=http://localhost:3000,https://memosaur.example.com
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000"
).split(",")

# ⚠️  SECURITY: Wildcard (*) nur für Single-User Local Development!
# Für Production/Multi-User: Setze CORS_ORIGINS in .env
if "*" in ALLOWED_ORIGINS:
    logger.warning("⚠️  CORS: Wildcard (*) aktiv - NUR für lokales Development!")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,  # Für JWT Cookies (Phase 2)
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup: SQLite initialisieren
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    # Elasticsearch Check
    from backend.rag.es_store import verify_elasticsearch
    verify_elasticsearch()

    from backend.db.database import init_db
    await init_db()
    logger.info("memosaur v2 gestartet.")

# ---------------------------------------------------------------------------
# v0-Router (Rückwärtskompatibilität – bleiben erhalten)
# ---------------------------------------------------------------------------

from backend.api.ingest import router as ingest_router
from backend.api.query import router as query_router
from backend.api.map import router as map_router
from backend.api.media import router as media_router

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(map_router)
app.include_router(media_router)

# ---------------------------------------------------------------------------
# Auth-Router
# ---------------------------------------------------------------------------

from backend.auth.oauth import router as oauth_router
from backend.auth.local import router as local_router

app.include_router(oauth_router)
app.include_router(local_router)

# ---------------------------------------------------------------------------
# v1-Router (token-aware, user-scoped)
# ---------------------------------------------------------------------------

from backend.api.v1.users      import router as v1_users_router
from backend.api.v1.sync       import router as v1_sync_router
from backend.api.v1.ingest     import router as v1_ingest_router
from backend.api.v1.query      import router as v1_query_router
from backend.api.v1.map        import router as v1_map_router
from backend.api.v1.media      import router as v1_media_router
from backend.api.v1.dictionary import router as v1_dictionary_router
from backend.api.v1.entities   import router as v1_entities_router
from backend.api.v1.webhook    import router as v1_webhook_router
from backend.api.v1.validation import router as v1_validation_router
from backend.api.v1.whatsapp   import router as v1_whatsapp_router

app.include_router(v1_users_router)
app.include_router(v1_sync_router)
app.include_router(v1_dictionary_router)
app.include_router(v1_entities_router)
app.include_router(v1_ingest_router)
app.include_router(v1_query_router)
app.include_router(v1_map_router)
app.include_router(v1_media_router)
app.include_router(v1_webhook_router)
app.include_router(v1_validation_router)
app.include_router(v1_whatsapp_router)

# ---------------------------------------------------------------------------
# Frontend (statische Dateien)
# ---------------------------------------------------------------------------

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_frontend() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/login.html")
    async def serve_login() -> FileResponse:
        """Serve login page for OAuth authentication."""
        return FileResponse(str(FRONTEND_DIR / "login.html"))

# Logs-Verzeichnis für WhatsApp-Logs
LOGS_DIR = BASE_DIR / "logs"
if LOGS_DIR.exists():
    app.mount("/logs", StaticFiles(directory=str(LOGS_DIR)), name="logs")

# ---------------------------------------------------------------------------
# Shared Endpunkte
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "memosaur", "version": "2.0.0"}


@app.get("/api/config")
async def get_config() -> dict:
    cfg_path = BASE_DIR / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    llm = dict(cfg.get("llm", {}))
    llm.pop("api_key", None)
    return {"llm": llm, "ingestion": cfg.get("ingestion", {}), "rag": cfg.get("rag", {})}


# ---------------------------------------------------------------------------
# Direktstart
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg_path = BASE_DIR / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        srv = yaml.safe_load(f).get("server", {})

    uvicorn.run(
        "backend.main:app",
        host=srv.get("host", "0.0.0.0"),
        port=srv.get("port", 8000),
        reload=srv.get("reload", True),
        app_dir=str(BASE_DIR),
    )
