"""
dictionary.py – /api/v1/dictionary

Stellt das Token-Wörterbuch für den Browser bereit.
Das Frontend importiert es beim ersten Start automatisch in die IndexedDB.

Nach erfolgreichem Import kann die Datei gelöscht werden.
Der Endpunkt ist immer verfügbar (gibt leeres Array zurück wenn keine Datei).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["v1/dictionary"])

BASE_DIR = Path(__file__).resolve().parents[3]
DICT_FILE = BASE_DIR / "data" / "migration_dictionary.json"


@router.get("/dictionary")
async def get_dictionary() -> JSONResponse:
    """
    Gibt das Token-Wörterbuch zurück.
    Das Frontend importiert es automatisch in IndexedDB beim ersten Start.
    """
    if not DICT_FILE.exists():
        return JSONResponse(content={"entries": [], "count": 0})

    try:
        entries = json.loads(DICT_FILE.read_text(encoding="utf-8"))
        logger.info("Wörterbuch ausgeliefert: %d Einträge", len(entries))
        return JSONResponse(content={"entries": entries, "count": len(entries)})
    except Exception as exc:
        logger.error("Fehler beim Lesen des Wörterbuchs: %s", exc)
        return JSONResponse(content={"entries": [], "count": 0})


@router.delete("/dictionary")
async def delete_dictionary() -> dict:
    """
    Löscht die lokale Wörterbuch-Datei nach erfolgreichem Browser-Import.
    Sollte vom Frontend nach dem Import aufgerufen werden.
    """
    if DICT_FILE.exists():
        DICT_FILE.unlink()
        logger.info("migration_dictionary.json gelöscht.")
        return {"status": "deleted"}
    return {"status": "not_found"}
