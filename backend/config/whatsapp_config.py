"""
WhatsApp Bot Configuration Management
======================================

Speichert und lädt WhatsApp-Bot-Konfiguration persistent in ChromaDB.

Die Konfiguration enthält:
- user_chat_id: Die WhatsApp-ID des Users (z.B. "4917012345678@c.us")
- bot_enabled: Ob der Bot aktiviert ist
- test_mode: Ob TEST_MODE aktiviert ist
"""

from backend.rag.store import get_collection
import logging

logger = logging.getLogger(__name__)

CONFIG_COLLECTION = "whatsapp_config"
CONFIG_ID = "bot_config_v1"


def get_whatsapp_config() -> dict:
    """
    Lädt die WhatsApp-Bot-Konfiguration aus ChromaDB.

    Returns:
        dict mit Feldern:
        - user_chat_id: str | None - WhatsApp-ID des Users
        - bot_enabled: bool - Bot aktiviert?
        - test_mode: bool - TEST_MODE aktiviert?
    """
    try:
        col = get_collection(CONFIG_COLLECTION)
        result = col.get(ids=[CONFIG_ID], include=["metadatas"])

        if result and result.get("ids") and len(result["ids"]) > 0:
            metadata = result["metadatas"][0]
            logger.info(f"WhatsApp Config geladen: {metadata}")
            return {
                "user_chat_id": metadata.get("user_chat_id"),
                "bot_enabled": metadata.get("bot_enabled", True),
                "test_mode": metadata.get("test_mode", False)
            }
        else:
            # Default-Config wenn noch nichts gespeichert
            logger.info("Keine WhatsApp Config gefunden, verwende Defaults")
            return {
                "user_chat_id": None,
                "bot_enabled": True,
                "test_mode": False
            }
    except Exception as e:
        logger.error(f"Fehler beim Laden der WhatsApp Config: {e}")
        return {
            "user_chat_id": None,
            "bot_enabled": True,
            "test_mode": False
        }


def set_whatsapp_config(user_chat_id: str = None, bot_enabled: bool = None, test_mode: bool = None) -> dict:
    """
    Speichert die WhatsApp-Bot-Konfiguration in ChromaDB.

    Nur übergebene Parameter werden aktualisiert, andere bleiben unverändert.

    Args:
        user_chat_id: WhatsApp-ID des Users (z.B. "4917012345678@c.us")
        bot_enabled: Bot aktiviert?
        test_mode: TEST_MODE aktiviert?

    Returns:
        dict mit der aktualisierten Config
    """
    try:
        # Aktuelle Config laden
        current_config = get_whatsapp_config()

        # Nur übergebene Werte aktualisieren
        if user_chat_id is not None:
            current_config["user_chat_id"] = user_chat_id
        if bot_enabled is not None:
            current_config["bot_enabled"] = bot_enabled
        if test_mode is not None:
            current_config["test_mode"] = test_mode

        # In ChromaDB speichern
        col = get_collection(CONFIG_COLLECTION)

        # Upsert (Update oder Insert)
        col.upsert(
            ids=[CONFIG_ID],
            documents=["WhatsApp Bot Configuration"],
            metadatas=[current_config]
        )

        logger.info(f"WhatsApp Config gespeichert: {current_config}")
        return current_config

    except Exception as e:
        logger.error(f"Fehler beim Speichern der WhatsApp Config: {e}")
        raise


def reset_whatsapp_config() -> dict:
    """
    Setzt die WhatsApp-Konfiguration auf Defaults zurück.

    Returns:
        dict mit der Reset-Config
    """
    return set_whatsapp_config(
        user_chat_id=None,
        bot_enabled=True,
        test_mode=False
    )
