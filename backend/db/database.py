"""
database.py – SQLite-Datenbankverbindung für memosaur.

Verwendet aiosqlite für async-Betrieb innerhalb von FastAPI.
Beim ersten Start wird das Schema automatisch angelegt und der
Default-User 'ManfredMustermann' gesetzt falls keine User existieren.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

import aiosqlite
import yaml

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
MIGRATION_SQL = Path(__file__).parent / "migrations" / "001_initial.sql"

# Default-User für Einzelbetrieb
DEFAULT_USER_ID   = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_NAME = "ManfredMustermann"

_db_path: Path | None = None


def _get_db_path() -> Path:
    global _db_path
    if _db_path is not None:
        return _db_path
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    data_dir = BASE_DIR / cfg["paths"]["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "memosaur.db"
    return _db_path


async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """FastAPI-Dependency: liefert eine DB-Verbindung pro Request."""
    async with aiosqlite.connect(str(_get_db_path())) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def init_db() -> None:
    """Initialisiert Schema und Default-User. Einmalig beim App-Start."""
    db_path = _get_db_path()
    logger.info("Initialisiere SQLite-Datenbank: %s", db_path)

    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Schema anwenden
        sql = MIGRATION_SQL.read_text(encoding="utf-8")
        await db.executescript(sql)
        await db.commit()

        # Default-User anlegen falls Tabelle leer
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await db.execute(
                "INSERT INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
                (DEFAULT_USER_ID, DEFAULT_USER_NAME, int(time.time())),
            )
            # Default-Consents: alles verweigert (Nutzer muss explizit zustimmen)
            for scope in ("biometric_photos", "gps", "messages"):
                await db.execute(
                    "INSERT INTO consents (user_id, scope, granted, granted_at) VALUES (?, ?, 0, ?)",
                    (DEFAULT_USER_ID, scope, int(time.time())),
                )
            await db.commit()
            logger.info("Default-User '%s' angelegt (ID: %s)", DEFAULT_USER_NAME, DEFAULT_USER_ID)
        else:
            logger.info("Datenbank bereits initialisiert (%d User).", count)
