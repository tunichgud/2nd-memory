"""
WhatsApp Import Plan Management
================================

Verwaltet den Import-Status von WhatsApp-Chats.
Speichert welche Chats bereits importiert wurden und welche noch ausstehen.
"""

from backend.rag.store import get_collection
from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

IMPORT_COLLECTION = "whatsapp_config"  # Nutzen wir die gleiche Collection
IMPORT_PLAN_ID = "import_plan_v1"


def get_import_plan() -> Dict:
    """
    Lädt den aktuellen Import-Plan aus ChromaDB.

    Returns:
        dict mit:
        - pending: List[str] - Chat-IDs die noch importiert werden müssen
        - completed: List[str] - Chat-IDs die bereits importiert wurden
        - in_progress: str | None - Chat-ID die gerade importiert wird
        - total_messages: int - Anzahl importierter Nachrichten
        - started_at: str | None - Timestamp wann Import gestartet wurde
        - last_updated: str | None - Timestamp der letzten Aktualisierung
    """
    try:
        col = get_collection(IMPORT_COLLECTION)
        result = col.get(ids=[IMPORT_PLAN_ID], include=["metadatas"])

        if result and result.get("ids") and len(result["ids"]) > 0:
            metadata = result["metadatas"][0]
            return {
                "pending": metadata.get("pending", []),
                "completed": metadata.get("completed", []),
                "in_progress": metadata.get("in_progress"),
                "total_messages": metadata.get("total_messages", 0),
                "started_at": metadata.get("started_at"),
                "last_updated": metadata.get("last_updated"),
            }
        else:
            # Kein Plan vorhanden
            return {
                "pending": [],
                "completed": [],
                "in_progress": None,
                "total_messages": 0,
                "started_at": None,
                "last_updated": None,
            }
    except Exception as e:
        logger.error(f"Fehler beim Laden des Import-Plans: {e}")
        return {
            "pending": [],
            "completed": [],
            "in_progress": None,
            "total_messages": 0,
            "started_at": None,
            "last_updated": None,
        }


def save_import_plan(
    pending: List[str] = None,
    completed: List[str] = None,
    in_progress: str = None,
    total_messages: int = None,
    started_at: str = None,
) -> Dict:
    """
    Speichert den Import-Plan in ChromaDB.

    Args:
        pending: Liste der noch zu importierenden Chat-IDs
        completed: Liste der bereits importierten Chat-IDs
        in_progress: Chat-ID die gerade importiert wird
        total_messages: Gesamtanzahl importierter Nachrichten
        started_at: Timestamp wann Import gestartet wurde

    Returns:
        dict mit der aktualisierten Config
    """
    try:
        # Aktuellen Plan laden
        current = get_import_plan()

        # Nur übergebene Werte aktualisieren
        if pending is not None:
            current["pending"] = pending
        if completed is not None:
            current["completed"] = completed
        if in_progress is not None:
            current["in_progress"] = in_progress
        if total_messages is not None:
            current["total_messages"] = total_messages
        if started_at is not None:
            current["started_at"] = started_at

        current["last_updated"] = datetime.now().isoformat()

        # In ChromaDB speichern
        col = get_collection(IMPORT_COLLECTION)
        col.upsert(
            ids=[IMPORT_PLAN_ID],
            documents=["WhatsApp Import Plan"],
            metadatas=[current],
        )

        logger.info(f"Import-Plan gespeichert: {len(current['completed'])} completed, {len(current['pending'])} pending")
        return current

    except Exception as e:
        logger.error(f"Fehler beim Speichern des Import-Plans: {e}")
        raise


def start_import(chat_ids: List[str]) -> Dict:
    """
    Startet einen neuen Import für die angegebenen Chats.

    Args:
        chat_ids: Liste der zu importierenden Chat-IDs

    Returns:
        dict mit dem initialisierten Import-Plan
    """
    return save_import_plan(
        pending=chat_ids,
        completed=[],
        in_progress=None,
        total_messages=0,
        started_at=datetime.now().isoformat(),
    )


def mark_chat_in_progress(chat_id: str) -> Dict:
    """
    Markiert einen Chat als "in progress".

    Args:
        chat_id: Die Chat-ID die gerade importiert wird

    Returns:
        dict mit aktualisiertem Plan
    """
    return save_import_plan(in_progress=chat_id)


def mark_chat_completed(chat_id: str, messages_imported: int) -> Dict:
    """
    Markiert einen Chat als abgeschlossen und entfernt ihn aus pending.

    Args:
        chat_id: Die Chat-ID die fertig importiert wurde
        messages_imported: Anzahl der importierten Nachrichten

    Returns:
        dict mit aktualisiertem Plan
    """
    plan = get_import_plan()

    # Entferne aus pending
    if chat_id in plan["pending"]:
        plan["pending"].remove(chat_id)

    # Füge zu completed hinzu
    if chat_id not in plan["completed"]:
        plan["completed"].append(chat_id)

    # In progress löschen
    if plan["in_progress"] == chat_id:
        plan["in_progress"] = None

    # Nachrichten-Counter erhöhen
    plan["total_messages"] += messages_imported

    return save_import_plan(
        pending=plan["pending"],
        completed=plan["completed"],
        in_progress=None,
        total_messages=plan["total_messages"],
    )


def reset_import_plan() -> Dict:
    """
    Setzt den Import-Plan zurück.

    Returns:
        dict mit leerem Plan
    """
    return save_import_plan(
        pending=[],
        completed=[],
        in_progress=None,
        total_messages=0,
        started_at=None,
    )


# ==============================================================================
# Per-Chat Timestamp Tracking (für Smart Deduplication)
# ==============================================================================

CHAT_TRACKING_PREFIX = "chat_tracking_"


def get_chat_last_import(chat_id: str) -> Optional[Dict]:
    """
    Holt den letzten Import-Timestamp für einen Chat.

    Args:
        chat_id: Die WhatsApp Chat-ID (z.B. "4917012345678@c.us")

    Returns:
        dict mit:
        - last_imported_timestamp: int - Unix timestamp der neuesten importierten Nachricht
        - last_imported_message_id: str - WhatsApp Message ID der neuesten Nachricht
        - first_import_run: str - ISO timestamp des ersten Imports
        - import_runs: int - Wie oft dieser Chat importiert wurde
        - total_messages_imported: int - Gesamtzahl importierter Nachrichten
        None wenn Chat noch nie importiert wurde
    """
    try:
        col = get_collection(IMPORT_COLLECTION)
        tracking_id = f"{CHAT_TRACKING_PREFIX}{chat_id}"
        result = col.get(ids=[tracking_id], include=["metadatas"])

        if result and result.get("ids") and len(result["ids"]) > 0:
            metadata = result["metadatas"][0]
            return {
                "last_imported_timestamp": metadata.get("last_imported_timestamp", 0),
                "last_imported_message_id": metadata.get("last_imported_message_id"),
                "first_import_run": metadata.get("first_import_run"),
                "import_runs": metadata.get("import_runs", 0),
                "total_messages_imported": metadata.get("total_messages_imported", 0),
            }
        else:
            return None
    except Exception as e:
        logger.error(f"Fehler beim Laden des Chat-Trackings für {chat_id}: {e}")
        return None


def update_chat_last_import(
    chat_id: str,
    timestamp: int,
    message_id: str,
    messages_imported: int = 0
) -> Dict:
    """
    Aktualisiert den letzten Import-Timestamp für einen Chat.

    Args:
        chat_id: Die WhatsApp Chat-ID
        timestamp: Unix timestamp der neuesten importierten Nachricht
        message_id: WhatsApp Message ID der neuesten Nachricht
        messages_imported: Anzahl der in diesem Run importierten Nachrichten

    Returns:
        dict mit aktualisierten Tracking-Daten
    """
    try:
        # Lade aktuelles Tracking
        current = get_chat_last_import(chat_id)

        if current is None:
            # Erster Import dieses Chats
            tracking_data = {
                "last_imported_timestamp": timestamp,
                "last_imported_message_id": message_id,
                "first_import_run": datetime.now().isoformat(),
                "import_runs": 1,
                "total_messages_imported": messages_imported,
            }
        else:
            # Update bestehendes Tracking
            tracking_data = {
                "last_imported_timestamp": timestamp,
                "last_imported_message_id": message_id,
                "first_import_run": current["first_import_run"],
                "import_runs": current["import_runs"] + 1,
                "total_messages_imported": current["total_messages_imported"] + messages_imported,
            }

        # Speichere in ChromaDB
        col = get_collection(IMPORT_COLLECTION)
        tracking_id = f"{CHAT_TRACKING_PREFIX}{chat_id}"
        col.upsert(
            ids=[tracking_id],
            documents=[f"Import tracking for chat {chat_id}"],
            metadatas=[tracking_data],
        )

        logger.info(f"Chat-Tracking aktualisiert für {chat_id}: {messages_imported} neue Nachrichten")
        return tracking_data

    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren des Chat-Trackings für {chat_id}: {e}")
        raise


def get_import_stats() -> Dict:
    """
    Liefert Statistiken über alle Imports.

    Returns:
        dict mit:
        - total_chats_tracked: int - Anzahl der getrackteten Chats
        - total_messages_imported: int - Gesamtzahl importierter Nachrichten
        - chats: List[Dict] - Liste mit Details pro Chat
    """
    try:
        col = get_collection(IMPORT_COLLECTION)
        # Hole alle chat_tracking_* Einträge
        all_data = col.get(include=["metadatas", "ids"])

        if not all_data or not all_data.get("ids"):
            return {
                "total_chats_tracked": 0,
                "total_messages_imported": 0,
                "chats": []
            }

        chats = []
        total_messages = 0

        for idx, doc_id in enumerate(all_data["ids"]):
            if doc_id.startswith(CHAT_TRACKING_PREFIX):
                chat_id = doc_id[len(CHAT_TRACKING_PREFIX):]
                metadata = all_data["metadatas"][idx]

                chat_data = {
                    "chat_id": chat_id,
                    "last_imported_timestamp": metadata.get("last_imported_timestamp", 0),
                    "last_imported_message_id": metadata.get("last_imported_message_id"),
                    "first_import_run": metadata.get("first_import_run"),
                    "import_runs": metadata.get("import_runs", 0),
                    "total_messages_imported": metadata.get("total_messages_imported", 0),
                }
                chats.append(chat_data)
                total_messages += chat_data["total_messages_imported"]

        return {
            "total_chats_tracked": len(chats),
            "total_messages_imported": total_messages,
            "chats": sorted(chats, key=lambda x: x["last_imported_timestamp"], reverse=True)
        }

    except Exception as e:
        logger.error(f"Fehler beim Laden der Import-Stats: {e}")
        return {
            "total_chats_tracked": 0,
            "total_messages_imported": 0,
            "chats": []
        }
