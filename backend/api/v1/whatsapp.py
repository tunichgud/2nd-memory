"""
WhatsApp Bot Configuration API
===============================

REST API Endpoints für WhatsApp-Bot-Konfiguration.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import logging
from datetime import datetime

from backend.config.whatsapp_config import (
    get_whatsapp_config,
    set_whatsapp_config,
    reset_whatsapp_config
)
from backend.rag.store import get_collection
from backend.config.whatsapp_import import (
    get_import_plan,
    start_import,
    mark_chat_in_progress,
    mark_chat_completed,
    reset_import_plan,
    get_chat_last_import,
    update_chat_last_import,
    get_import_stats
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


# ===== Pydantic Models =====

class WhatsAppConfigResponse(BaseModel):
    """Response Model für WhatsApp Config"""
    user_chat_id: Optional[str]
    bot_enabled: bool
    test_mode: bool
    configured: bool  # True wenn user_chat_id gesetzt ist


class SetUserChatRequest(BaseModel):
    """Request Model zum Setzen der User-Chat-ID"""
    chat_id: str


class SetBotEnabledRequest(BaseModel):
    """Request Model zum Aktivieren/Deaktivieren des Bots"""
    enabled: bool


class SetTestModeRequest(BaseModel):
    """Request Model zum Aktivieren/Deaktivieren des TEST_MODE"""
    enabled: bool


# ===== API Endpoints =====

@router.get("/config", response_model=WhatsAppConfigResponse)
async def get_config():
    """
    GET /api/whatsapp/config

    Gibt die aktuelle WhatsApp-Bot-Konfiguration zurück.
    """
    config = get_whatsapp_config()

    return WhatsAppConfigResponse(
        user_chat_id=config["user_chat_id"],
        bot_enabled=config["bot_enabled"],
        test_mode=config["test_mode"],
        configured=config["user_chat_id"] is not None
    )


@router.post("/config/user-chat", response_model=WhatsAppConfigResponse)
async def set_user_chat(request: SetUserChatRequest):
    """
    POST /api/whatsapp/config/user-chat

    Setzt die WhatsApp-ID des Users (z.B. "4917012345678@c.us").
    Der Bot antwortet nur auf Nachrichten an diesen User.

    Body: {"chat_id": "4917012345678@c.us"}
    """
    if not request.chat_id:
        raise HTTPException(status_code=400, detail="chat_id darf nicht leer sein")

    # Validiere Format (optional)
    if "@" not in request.chat_id:
        raise HTTPException(
            status_code=400,
            detail="Ungültiges Format. Erwartet: '4917012345678@c.us' oder '4917012345678@g.us'"
        )

    config = set_whatsapp_config(user_chat_id=request.chat_id)

    logger.info(f"User-Chat-ID gesetzt: {request.chat_id}")

    return WhatsAppConfigResponse(
        user_chat_id=config["user_chat_id"],
        bot_enabled=config["bot_enabled"],
        test_mode=config["test_mode"],
        configured=True
    )


@router.delete("/config/user-chat", response_model=WhatsAppConfigResponse)
async def delete_user_chat():
    """
    DELETE /api/whatsapp/config/user-chat

    Entfernt die User-Chat-ID (Reset).
    """
    config = set_whatsapp_config(user_chat_id=None)

    logger.info("User-Chat-ID entfernt")

    return WhatsAppConfigResponse(
        user_chat_id=None,
        bot_enabled=config["bot_enabled"],
        test_mode=config["test_mode"],
        configured=False
    )


@router.post("/config/bot-enabled", response_model=WhatsAppConfigResponse)
async def set_bot_enabled(request: SetBotEnabledRequest):
    """
    POST /api/whatsapp/config/bot-enabled

    Aktiviert/Deaktiviert den Bot (Master-Switch).

    Body: {"enabled": true}
    """
    config = set_whatsapp_config(bot_enabled=request.enabled)

    logger.info(f"Bot {'aktiviert' if request.enabled else 'deaktiviert'}")

    return WhatsAppConfigResponse(
        user_chat_id=config["user_chat_id"],
        bot_enabled=config["bot_enabled"],
        test_mode=config["test_mode"],
        configured=config["user_chat_id"] is not None
    )


@router.post("/config/test-mode", response_model=WhatsAppConfigResponse)
async def set_test_mode(request: SetTestModeRequest):
    """
    POST /api/whatsapp/config/test-mode

    Aktiviert/Deaktiviert TEST_MODE.

    Body: {"enabled": true}
    """
    config = set_whatsapp_config(test_mode=request.enabled)

    logger.info(f"TEST_MODE {'aktiviert' if request.enabled else 'deaktiviert'}")

    return WhatsAppConfigResponse(
        user_chat_id=config["user_chat_id"],
        bot_enabled=config["bot_enabled"],
        test_mode=config["test_mode"],
        configured=config["user_chat_id"] is not None
    )


@router.post("/config/reset", response_model=WhatsAppConfigResponse)
async def reset_config():
    """
    POST /api/whatsapp/config/reset

    Setzt die komplette Konfiguration auf Defaults zurück.
    """
    config = reset_whatsapp_config()

    logger.info("WhatsApp Config zurückgesetzt")

    return WhatsAppConfigResponse(
        user_chat_id=None,
        bot_enabled=config["bot_enabled"],
        test_mode=config["test_mode"],
        configured=False
    )


# ===== WhatsApp Message Ingestion =====

class WhatsAppMessageRequest(BaseModel):
    """Request Model für WhatsApp-Nachrichten"""
    message_id: str
    chat_id: str
    chat_name: str
    sender: str
    text: str
    timestamp: int
    is_from_me: bool
    has_media: bool = False
    type: str = "chat"


def save_whatsapp_message_sync(message_data: dict):
    """
    Speichert eine WhatsApp-Nachricht in ChromaDB (synchron, für Background-Task).
    """
    try:
        col = get_collection("messages")

        # Konvertiere Timestamp zu datetime
        timestamp_dt = datetime.fromtimestamp(message_data["timestamp"])

        metadata = {
            "chat_id": message_data["chat_id"],
            "chat_name": message_data["chat_name"],
            "sender": message_data["sender"],
            "timestamp": timestamp_dt.isoformat(),
            "is_from_me": message_data["is_from_me"],
            "has_media": message_data["has_media"],
            "type": message_data["type"],
            "source": "whatsapp"
        }

        col.upsert(
            ids=[message_data["message_id"]],
            documents=[message_data["text"]],
            metadatas=[metadata]
        )

        logger.debug(f"WhatsApp-Nachricht gespeichert: {message_data['message_id']}")

    except Exception as e:
        logger.error(f"Fehler beim Speichern der WhatsApp-Nachricht: {e}")
        raise


@router.post("/message")
async def ingest_whatsapp_message(
    message: WhatsAppMessageRequest,
    background_tasks: BackgroundTasks
):
    """
    POST /api/whatsapp/message

    Speichert eine WhatsApp-Nachricht asynchron in ChromaDB.
    Die Verarbeitung läuft im Hintergrund, damit der Client nicht warten muss.
    """
    # Konvertiere zu dict für Background-Task
    message_data = message.dict()

    # Führe Speicherung im Hintergrund aus
    background_tasks.add_task(save_whatsapp_message_sync, message_data)

    return {
        "status": "queued",
        "message_id": message.message_id
    }


# ===== WhatsApp Import Plan Management =====

@router.get("/import-plan")
async def get_import_plan_status():
    """
    GET /api/whatsapp/import-plan
    
    Gibt den aktuellen Import-Plan zurück.
    """
    plan = get_import_plan()
    
    return {
        "pending_count": len(plan["pending"]),
        "completed_count": len(plan["completed"]),
        "in_progress": plan["in_progress"],
        "total_messages": plan["total_messages"],
        "started_at": plan["started_at"],
        "last_updated": plan["last_updated"],
        "pending_chats": plan["pending"],
        "completed_chats": plan["completed"],
    }


@router.post("/import-plan/start")
async def start_import_plan(chat_ids: List[str]):
    """
    POST /api/whatsapp/import-plan/start
    
    Startet einen neuen Import-Plan für die angegebenen Chat-IDs.
    
    Body: ["chat_id_1", "chat_id_2", ...]
    """
    plan = start_import(chat_ids)
    
    logger.info(f"Import-Plan gestartet für {len(chat_ids)} Chats")
    
    return {
        "status": "started",
        "total_chats": len(chat_ids),
        "plan": plan
    }


@router.post("/import-plan/mark-in-progress")
async def mark_in_progress(chat_id: str):
    """
    POST /api/whatsapp/import-plan/mark-in-progress
    
    Markiert einen Chat als "in progress".
    
    Body: "chat_id_xyz@c.us"
    """
    plan = mark_chat_in_progress(chat_id)
    
    return {"status": "in_progress", "chat_id": chat_id, "plan": plan}


@router.post("/import-plan/mark-completed")
async def mark_completed(chat_id: str, messages_imported: int = 0):
    """
    POST /api/whatsapp/import-plan/mark-completed
    
    Markiert einen Chat als abgeschlossen.
    
    Query params: chat_id, messages_imported
    """
    plan = mark_chat_completed(chat_id, messages_imported)
    
    return {"status": "completed", "chat_id": chat_id, "plan": plan}


@router.post("/import-plan/reset")
async def reset_plan():
    """
    POST /api/whatsapp/import-plan/reset

    Setzt den Import-Plan zurück.
    """
    plan = reset_import_plan()

    logger.info("Import-Plan zurückgesetzt")

    return {"status": "reset", "plan": plan}


# ===== Per-Chat Timestamp Tracking (Smart Deduplication) =====

@router.get("/import-plan/chat/{chat_id}/last-import")
async def get_chat_last_import_endpoint(chat_id: str):
    """
    GET /api/whatsapp/import-plan/chat/{chat_id}/last-import

    Gibt den letzten Import-Timestamp für einen Chat zurück.
    Wird von index.js verwendet für Smart Deduplication.

    Returns:
        - last_imported_timestamp: Unix timestamp der neuesten importierten Nachricht
        - last_imported_message_id: WhatsApp Message ID
        - first_import_run: Wann der Chat erstmalig importiert wurde
        - import_runs: Wie oft dieser Chat importiert wurde
        - total_messages_imported: Gesamtzahl importierter Nachrichten

        Null wenn Chat noch nie importiert wurde.
    """
    tracking = get_chat_last_import(chat_id)

    if tracking is None:
        return {
            "chat_id": chat_id,
            "last_imported_timestamp": 0,
            "last_imported_message_id": None,
            "first_import_run": None,
            "import_runs": 0,
            "total_messages_imported": 0,
            "never_imported": True
        }

    return {
        "chat_id": chat_id,
        **tracking,
        "never_imported": False
    }


class UpdateChatTimestampRequest(BaseModel):
    """Request Model für Timestamp-Updates"""
    timestamp: int
    message_id: str


@router.post("/import-plan/chat/{chat_id}/update-timestamp")
async def update_chat_timestamp_endpoint(
    chat_id: str,
    request: UpdateChatTimestampRequest
):
    """
    POST /api/whatsapp/import-plan/chat/{chat_id}/update-timestamp

    Aktualisiert den letzten Import-Timestamp für einen Chat.
    Wird von index.js nach jedem Import aufgerufen.

    Body: {
        "timestamp": 1741814400,  # Unix timestamp
        "message_id": "true_4917012345678@c.us_3EB0ABC123DEF456"
    }
    """
    try:
        # Wir tracken nur den neuesten Timestamp, nicht die Anzahl der Nachrichten
        # (das macht index.js bereits)
        tracking = update_chat_last_import(
            chat_id=chat_id,
            timestamp=request.timestamp,
            message_id=request.message_id,
            messages_imported=0  # Wird vom Caller nicht übergeben
        )

        logger.info(f"Chat-Timestamp aktualisiert: {chat_id} -> {request.timestamp}")

        return {
            "status": "updated",
            "chat_id": chat_id,
            **tracking
        }
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren des Chat-Timestamps: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import-plan/stats")
async def get_import_stats_endpoint():
    """
    GET /api/whatsapp/import-plan/stats

    Gibt Statistiken über alle Imports zurück.

    Returns:
        - total_chats_tracked: Anzahl der getrackteten Chats
        - total_messages_imported: Gesamtzahl importierter Nachrichten
        - chats: Liste mit Details pro Chat (sortiert nach letztem Import)
    """
    stats = get_import_stats()

    return {
        "status": "ok",
        **stats
    }
