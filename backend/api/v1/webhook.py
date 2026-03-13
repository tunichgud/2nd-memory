"""
webhook.py – /api/v1/webhook

Empfängt Nachrichten von der WhatsApp-Brücke (index.js).
Führt eine RAG-Abfrage für den Default-User aus und gibt die Antwort zurück.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite

from backend.db.database import get_db, DEFAULT_USER_ID
from backend.rag.retriever_v2 import answer_v2

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["v1/webhook"])

class WebhookRequest(BaseModel):
    sender: str
    text: str
    is_incoming: bool = True

class WebhookResponse(BaseModel):
    status: str
    answer: str | None = None
    query_id: str | None = None

@router.post("/webhook", response_model=WebhookResponse)
async def whatsapp_webhook(
    req: WebhookRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Empfängt eine WhatsApp-Nachricht und antwortet mit der AI-Generierung.
    Nutzt den Default-User 'ManfredMustermann'.
    """
    logger.info("WhatsApp Webhook empfangen von %s: %s", req.sender, req.text)

    # User prüfen (Default-User)
    cursor = await db.execute("SELECT id FROM users WHERE id = ? AND is_active = 1", (DEFAULT_USER_ID,))
    if not await cursor.fetchone():
        logger.error("Default-User %s nicht gefunden oder inaktiv", DEFAULT_USER_ID)
        raise HTTPException(status_code=404, detail="Default-User nicht gefunden")

    try:
        import asyncio
        loop = asyncio.get_event_loop()

        # Markierung für Bot-Antworten
        BOT_PREFIX = "🦕"
        is_bot_msg = req.text.startswith(BOT_PREFIX)

        # 1. Nachricht in DB indexieren (Live-Ingestion)
        # Wir indexieren ALLES, um den vollen Chat-Verlauf im Gedächtnis zu haben.
        from backend.rag.embedder import embed_single
        from backend.rag.store_v2 import upsert_documents_v2
        from datetime import datetime
        import uuid

        now = datetime.now()
        date_iso = now.strftime("%d.%m.%Y %H:%M:%S")
        ts = int(now.timestamp())
        
        # Sender-Name für die DB aufbereiten
        sender_display = "KI (2nd Memory)" if is_bot_msg else (req.sender if req.is_incoming else "Ich (Manfred)")
        
        doc_text = f"WhatsApp [{date_iso}] {sender_display}: {req.text}"
        
        embedding = await loop.run_in_executor(
            None, lambda: embed_single(doc_text)
        )
        
        meta = {
            "source": "whatsapp",
            "chat_name": "WhatsApp Live",
            "date_ts": ts,
            "date_iso": date_iso,
            "lat": 0.0,
            "lon": 0.0,
            "persons": sender_display,
            "mentioned_persons": sender_display,
            "user_id": DEFAULT_USER_ID,
            "is_bot": is_bot_msg
        }
        
        upsert_documents_v2(
            "messages",
            [f"wa_live_{uuid.uuid4().hex[:8]}"],
            [doc_text],
            [embedding],
            [meta],
        )
        logger.info("WhatsApp Nachricht indexiert (%s): %s", sender_display, req.text[:50])

        # 2. RAG-Abfrage starten (v2 Pipeline)
        # Wir antworten NUR auf echte eingehende Nachrichten, die NICHT von der KI selbst sind.
        answer = None
        query_id = None
        if req.is_incoming and not is_bot_msg:
            result = await loop.run_in_executor(
                None,
                lambda: answer_v2(
                    masked_query=req.text,
                    user_id=DEFAULT_USER_ID,
                    person_tokens=[],
                    location_tokens=[],
                    collections=None
                )
            )
            answer = result.get("answer")
            query_id = result.get("query_id")

        return WebhookResponse(status="success", answer=answer, query_id=query_id)

    except Exception as exc:
        logger.exception("Fehler im WhatsApp Webhook")
        return WebhookResponse(status="error", answer=None)
