"""
database.py – SQLite-Datenbankverbindung für 2nd Memory.

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
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

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
    _db_path = data_dir / "2nd-memory.db"
    return _db_path


async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """FastAPI-Dependency: liefert eine DB-Verbindung pro Request."""
    async with aiosqlite.connect(str(_get_db_path())) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Führt alle ausstehenden Migrationen aus."""
    # Erstelle schema_migrations Tabelle falls nicht vorhanden (Bootstrap für neue DBs)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
    """)
    await db.commit()

    # Hole aktuelle Schema-Version
    cursor = await db.execute("SELECT MAX(version) FROM schema_migrations")
    row = await cursor.fetchone()
    current_version = row[0] if row and row[0] else 0

    # Finde alle Migration-Files
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for migration_file in migration_files:
        # Extrahiere Version aus Filename (z.B. "001_initial.sql" → 1)
        try:
            version = int(migration_file.stem.split('_')[0])
        except (ValueError, IndexError):
            logger.warning("Überspringe ungültige Migration: %s", migration_file.name)
            continue

        # Nur neue Migrationen ausführen
        if version > current_version:
            logger.info("Führe Migration %03d aus: %s", version, migration_file.name)
            sql = migration_file.read_text(encoding="utf-8")
            await db.executescript(sql)
            await db.commit()
            logger.info("Migration %03d erfolgreich angewendet", version)


async def init_db() -> None:
    """Initialisiert Schema und Default-User. Einmalig beim App-Start."""
    db_path = _get_db_path()
    logger.info("Initialisiere SQLite-Datenbank: %s", db_path)

    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Führe alle Migrationen aus
        await _run_migrations(db)

        # Default-User anlegen falls Tabelle leer
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await db.execute(
                "INSERT INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
                (DEFAULT_USER_ID, DEFAULT_USER_NAME, int(time.time())),
            )
            await db.commit()
            logger.info("Default-User '%s' angelegt (ID: %s)", DEFAULT_USER_NAME, DEFAULT_USER_ID)
        else:
            logger.info("Datenbank bereits initialisiert (%d User).", count)
