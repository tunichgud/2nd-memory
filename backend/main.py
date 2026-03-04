"""
main.py – FastAPI Hauptanwendung für memosaur.

v0-Endpunkte (/api/*) bleiben erhalten (Rückwärtskompatibilität).
v1-Endpunkte (/api/v1/*) sind token-aware und user-scoped.

Start: python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="memosaur",
    description="Persönliches Gedächtnis-System – Privacy-First RAG",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup: SQLite initialisieren
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
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
# v1-Router (token-aware, user-scoped)
# ---------------------------------------------------------------------------

from backend.api.v1.users   import router as v1_users_router
from backend.api.v1.consent import router as v1_consent_router
from backend.api.v1.sync    import router as v1_sync_router
from backend.api.v1.ingest  import router as v1_ingest_router
from backend.api.v1.query   import router as v1_query_router
from backend.api.v1.map     import router as v1_map_router
from backend.api.v1.media   import router as v1_media_router

app.include_router(v1_users_router)
app.include_router(v1_consent_router)
app.include_router(v1_sync_router)
app.include_router(v1_ingest_router)
app.include_router(v1_query_router)
app.include_router(v1_map_router)
app.include_router(v1_media_router)

# ---------------------------------------------------------------------------
# Frontend (statische Dateien)
# ---------------------------------------------------------------------------

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_frontend() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

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
