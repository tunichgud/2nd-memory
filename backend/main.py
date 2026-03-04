"""
main.py – FastAPI Hauptanwendung für memosaur.

Start: python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
oder:  python backend/main.py
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

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Projektpfad sicherstellen
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# ---------------------------------------------------------------------------
# App initialisieren
# ---------------------------------------------------------------------------

app = FastAPI(
    title="memosaur",
    description="Persönliches Gedächtnis-System: Fotos, Nachrichten, Geodaten",
    version="0.1.0",
)

# CORS (für lokale Entwicklung)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Router einbinden
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
# Frontend statische Dateien
# ---------------------------------------------------------------------------

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_frontend() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "memosaur"}


@app.get("/api/config")
async def get_config() -> dict:
    """Gibt die aktuelle (nicht-sensitive) Konfiguration zurück."""
    cfg_path = BASE_DIR / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Sensible Felder entfernen
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
