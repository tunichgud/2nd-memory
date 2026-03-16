"""
WhatsApp Bot Configuration Management
======================================

Speichert und lädt WhatsApp-Bot-Konfiguration persistent in SQLite
(Tabelle: whatsapp_config).

Die Konfiguration enthält:
- user_chat_id: Die WhatsApp-ID des Users (z.B. "4917012345678@c.us")
- bot_enabled: Ob der Bot aktiviert ist
- test_mode: Ob TEST_MODE aktiviert ist
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_db_path: Optional[Path] = None


def _get_db_path() -> Path:
    """Gibt den Pfad zur SQLite-Datenbank zurück (liest config.yaml einmalig).

    Returns:
        Path zur memosaur.db Datei.
    """
    global _db_path
    if _db_path is not None:
        return _db_path
    base_dir = Path(__file__).resolve().parents[2]
    with open(base_dir / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    data_dir = base_dir / cfg["paths"]["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "memosaur.db"
    return _db_path


def get_config_value(key: str) -> Optional[str]:
    """Liest einen einzelnen Konfigurationswert aus SQLite.

    Args:
        key: Konfigurationsschlüssel (z.B. "user_chat_id").

    Returns:
        Wert als String oder None wenn nicht vorhanden.
    """
    try:
        with sqlite3.connect(str(_get_db_path())) as conn:
            cursor = conn.execute(
                "SELECT value FROM whatsapp_config WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error("Fehler beim Lesen von whatsapp_config[%s]: %s", key, e)
        return None


def set_config_value(key: str, value: str) -> None:
    """Schreibt einen einzelnen Konfigurationswert in SQLite (upsert).

    Args:
        key: Konfigurationsschlüssel.
        value: Wert als String.
    """
    try:
        with sqlite3.connect(str(_get_db_path())) as conn:
            conn.execute(
                "INSERT INTO whatsapp_config (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
    except Exception as e:
        logger.error("Fehler beim Schreiben von whatsapp_config[%s]: %s", key, e)
        raise


def get_all_config() -> dict:
    """Liest alle Konfigurationswerte aus SQLite.

    Returns:
        Dict mit allen gespeicherten Key-Value-Paaren.
    """
    try:
        with sqlite3.connect(str(_get_db_path())) as conn:
            cursor = conn.execute("SELECT key, value FROM whatsapp_config")
            return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        logger.error("Fehler beim Lesen der gesamten whatsapp_config: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Public API (bestehende Schnittstelle bleibt unverändert)
# ---------------------------------------------------------------------------

def get_whatsapp_config() -> dict:
    """Lädt die WhatsApp-Bot-Konfiguration aus SQLite.

    Returns:
        dict mit Feldern:
        - user_chat_id: str | None — WhatsApp-ID des Users
        - bot_enabled: bool — Bot aktiviert?
        - test_mode: bool — TEST_MODE aktiviert?
    """
    try:
        raw = get_all_config()
        user_chat_id = raw.get("user_chat_id") or None
        bot_enabled_raw = raw.get("bot_enabled", "true")
        test_mode_raw = raw.get("test_mode", "false")

        # Werte wurden als JSON-kompatible Strings gespeichert
        bot_enabled = json.loads(bot_enabled_raw) if isinstance(bot_enabled_raw, str) else bool(bot_enabled_raw)
        test_mode = json.loads(test_mode_raw) if isinstance(test_mode_raw, str) else bool(test_mode_raw)

        config = {
            "user_chat_id": user_chat_id,
            "bot_enabled": bot_enabled,
            "test_mode": test_mode,
        }
        logger.debug("WhatsApp Config geladen: %s", config)
        return config
    except Exception as e:
        logger.error("Fehler beim Laden der WhatsApp Config: %s", e)
        return {"user_chat_id": None, "bot_enabled": True, "test_mode": False}


_SENTINEL = object()


def set_whatsapp_config(
    user_chat_id: Any = _SENTINEL,
    bot_enabled: Optional[bool] = None,
    test_mode: Optional[bool] = None,
) -> dict:
    """Speichert die WhatsApp-Bot-Konfiguration in SQLite.

    Nur übergebene Parameter werden aktualisiert, andere bleiben unverändert.
    user_chat_id=None löscht die gespeicherte Chat-ID.

    Args:
        user_chat_id: WhatsApp-ID des Users (z.B. "4917012345678@c.us").
            Wenn None übergeben wird, wird die ID gelöscht.
            Wenn nicht übergeben (Sentinel), bleibt der Wert unverändert.
        bot_enabled: Bot aktiviert?
        test_mode: TEST_MODE aktiviert?

    Returns:
        dict mit der aktualisierten Config.
    """
    try:
        current = get_whatsapp_config()

        if user_chat_id is not _SENTINEL:
            # Explizit übergeben: entweder neuer Wert oder None (= löschen)
            current["user_chat_id"] = user_chat_id
            set_config_value("user_chat_id", user_chat_id if user_chat_id is not None else "")

        if bot_enabled is not None:
            current["bot_enabled"] = bot_enabled
            set_config_value("bot_enabled", json.dumps(bot_enabled))

        if test_mode is not None:
            current["test_mode"] = test_mode
            set_config_value("test_mode", json.dumps(test_mode))

        logger.info("WhatsApp Config gespeichert: %s", current)
        return current
    except Exception as e:
        logger.error("Fehler beim Speichern der WhatsApp Config: %s", e)
        raise


def reset_whatsapp_config() -> dict:
    """Setzt die WhatsApp-Konfiguration auf Defaults zurück.

    Returns:
        dict mit der Reset-Config.
    """
    try:
        set_config_value("user_chat_id", "")
        set_config_value("bot_enabled", "true")
        set_config_value("test_mode", "false")
        config = {"user_chat_id": None, "bot_enabled": True, "test_mode": False}
        logger.info("WhatsApp Config zurückgesetzt")
        return config
    except Exception as e:
        logger.error("Fehler beim Zurücksetzen der WhatsApp Config: %s", e)
        raise
