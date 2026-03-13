"""
whatsapp.py – WhatsApp Chat Export Ingestion (Stub).

Unterstützt WhatsApp-Exporte im TXT-Format (Android/iOS).

Format einer exportierten Zeile:
  DD.MM.YY, HH:MM - Name: Nachrichtentext
  oder (älteres Format):
  [DD.MM.YY, HH:MM:SS] Name: Nachrichtentext
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Muster für WhatsApp-Nachrichten
_PATTERNS = [
    # Android: "01.01.25, 12:00 - Name: Text"
    re.compile(r"^(\d{2}\.\d{2}\.\d{2,4}),\s*(\d{2}:\d{2}(?::\d{2})?)\s*[-–]\s*(.+?):\s*(.+)$"),
    # iOS: "[01.01.25, 12:00:00] Name: Text"
    re.compile(r"^\[(\d{2}\.\d{2}\.\d{2,4}),\s*(\d{2}:\d{2}(?::\d{2})?)\]\s*(.+?):\s*(.+)$"),
]

SYSTEM_MESSAGES = {
    "<Medien weggelassen>",
    "<Media omitted>",
    "Nachrichten und Anrufe sind Ende-zu-Ende-verschlüsselt",
    "Messages and calls are end-to-end encrypted",
}


def parse_whatsapp_export(file_path: Path) -> list[dict]:
    """Parst eine WhatsApp TXT-Exportdatei und gibt eine Liste von Nachrichten zurück."""
    messages = []
    current: dict | None = None

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.error("Kann WhatsApp-Export nicht lesen: %s", exc)
        return []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        matched = False
        for pattern in _PATTERNS:
            m = pattern.match(line)
            if m:
                # Vorherige Nachricht speichern
                if current:
                    messages.append(current)

                date_str, time_str, sender, content = m.groups()
                content = content.strip()

                # Systemnachrichten überspringen
                if any(s in content for s in SYSTEM_MESSAGES):
                    current = None
                    matched = True
                    break

                # Datum parsen
                ts = 0
                try:
                    fmt = "%d.%m.%y" if len(date_str.split(".")[-1]) == 2 else "%d.%m.%Y"
                    time_fmt = "%H:%M:%S" if time_str.count(":") == 2 else "%H:%M"
                    dt = datetime.strptime(f"{date_str} {time_str}", f"{fmt} {time_fmt}")
                    ts = int(dt.timestamp())
                except ValueError:
                    pass

                current = {
                    "date_ts": ts,
                    "date_str": f"{date_str} {time_str}",
                    "sender": sender,
                    "content": content,
                }
                matched = True
                break

        if not matched and current:
            # Fortsetzungszeile einer mehrzeiligen Nachricht
            current["content"] += " " + line

    if current:
        messages.append(current)

    return messages


def ingest_whatsapp(
    chat_file: Path,
    chat_name: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    reset: bool = False,
    user_id: str = "00000000-0000-0000-0000-000000000001",
) -> dict:
    """Importiert einen WhatsApp-Chat in ChromaDB.

    Args:
        chat_file: Pfad zur exportierten _chat.txt Datei
        chat_name: Optionaler Name des Chats (z.B. Gruppenname)
        progress_callback: Fortschritts-Callback
        reset: Collection vorher leeren
        user_id: ID des Benutzers
    """
    from backend.rag.embedder import embed_single
    from backend.rag.store import upsert_documents, reset_collection

    if not chat_file.exists():
        logger.error("WhatsApp-Export nicht gefunden: %s", chat_file)
        return {"total": 0, "success": 0, "errors": 1}

    name = chat_name or chat_file.stem
    messages = parse_whatsapp_export(chat_file)
    total = len(messages)
    logger.info("%d WhatsApp-Nachrichten in '%s' gefunden.", total, name)

    if reset:
        reset_collection("messages")

    stats = {"total": total, "success": 0, "errors": 0}
    ids, documents, embeddings, metadatas = [], [], [], []

    # Nachrichten in Gruppen von max. 10 zusammenfassen (für besseren Kontext)
    CHUNK_SIZE = 10
    for chunk_idx in range(0, total, CHUNK_SIZE):
        chunk = messages[chunk_idx:chunk_idx + CHUNK_SIZE]
        chunk_num = chunk_idx // CHUNK_SIZE + 1

        status = f"WhatsApp [{chunk_num}]: Nachrichten {chunk_idx+1}–{min(chunk_idx+CHUNK_SIZE, total)}"
        if progress_callback:
            progress_callback(chunk_idx + 1, total, status)

        # Chunk-Text erstellen
        lines = []
        for msg in chunk:
            lines.append(f"[{msg['date_str']}] {msg['sender']}: {msg['content']}")
        doc_text = f"WhatsApp Chat '{name}':\n" + "\n".join(lines)

        try:
            embedding = embed_single(doc_text)
        except Exception as exc:
            logger.error("Embedding-Fehler für Chunk %d: %s", chunk_num, exc)
            stats["errors"] += 1
            continue

        first_ts = chunk[0]["date_ts"] if chunk else 0
        senders = list({m["sender"] for m in chunk})

        # Erwähnte Personen extrahieren (Absender + im Text erwähnte Namen)
        from backend.ingestion.persons import extract_mentioned_persons
        try:
            mentioned = extract_mentioned_persons(doc_text, sender_names=senders)
        except Exception as exc:
            logger.warning("Personen-Extraktion fehlgeschlagen: %s", exc)
            mentioned = senders

        chroma_meta = {
            "source": "whatsapp",
            "chat_name": name,
            "date_ts": first_ts,
            "date_iso": chunk[0].get("date_str", "") if chunk else "",
            "lat": 0.0,
            "lon": 0.0,
            "persons": ",".join(senders),
            "mentioned_persons": ",".join(mentioned),
            "user_id": user_id,
        }

        ids.append(f"wa_{name[:20]}_{chunk_idx:05d}")
        documents.append(doc_text)
        embeddings.append(embedding)
        metadatas.append(chroma_meta)
        stats["success"] += len(chunk)

        # In Batches speichern (100 Chunks = 1000 Nachrichten pro Batch)
        if len(ids) >= 100:
            from backend.rag.store import upsert_documents
            from backend.rag.es_store import upsert_documents_es, reset_es_index
            
            if reset:
                reset_es_index("messages")
                reset = False # Nur einmal beim ersten Batch
                
            upsert_documents("messages", ids, documents, embeddings, metadatas)
            upsert_documents_es("messages", ids, documents, embeddings, metadatas)
            ids, documents, embeddings, metadatas = [], [], [], []

    if ids:
        from backend.rag.store import upsert_documents
        from backend.rag.es_store import upsert_documents_es, reset_es_index
        
        if reset:
            reset_es_index("messages")
            
        upsert_documents("messages", ids, documents, embeddings, metadatas)
        upsert_documents_es("messages", ids, documents, embeddings, metadatas)

    logger.info("WhatsApp-Ingestion abgeschlossen: %s", stats)
    return stats
