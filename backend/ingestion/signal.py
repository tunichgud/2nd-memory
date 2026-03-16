"""
signal.py – Signal Messenger Export Ingestion (Stub).

Unterstützt Signal Desktop Backup (JSON-Format).

Signal Desktop kann über Einstellungen > Chats > Chats exportieren
ein Zip-Archiv mit messages.json erstellen.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


def ingest_signal(
    export_path: Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
    reset: bool = False,
) -> dict:
    """Importiert Signal-Nachrichten aus einem JSON-Export.

    Args:
        export_path: Pfad zur messages.json oder zum entpackten Export-Ordner
        progress_callback: Fortschritts-Callback
        reset: Collection vorher leeren

    Returns:
        Statistiken: total, success, errors
    """
    from backend.rag.embedder import embed_single
    from backend.rag.store_es import upsert_documents_v2
    from backend.rag.es_store import reset_es_index

    # messages.json finden
    if export_path.is_dir():
        msg_file = export_path / "messages.json"
    else:
        msg_file = export_path

    if not msg_file.exists():
        logger.error("Signal-Export nicht gefunden: %s", msg_file)
        return {"total": 0, "success": 0, "errors": 1}

    data = json.loads(msg_file.read_text(encoding="utf-8"))

    # Signal Export Format: Liste von Konversationen
    # Jede Konversation hat: name, messages[]
    # Jede Nachricht hat: type, body, timestamp, author (optional)
    conversations = data if isinstance(data, list) else data.get("conversations", [])
    total_msgs = sum(len(c.get("messages", [])) for c in conversations)
    logger.info("%d Signal-Nachrichten in %d Konversationen.", total_msgs, len(conversations))

    if reset:
        reset_es_index("messages")

    stats = {"total": total_msgs, "success": 0, "errors": 0}
    ids, documents, embeddings, metadatas = [], [], [], []

    processed = 0
    CHUNK_SIZE = 10

    for conv in conversations:
        conv_name = conv.get("name", conv.get("id", "Unbekannt"))
        messages = conv.get("messages", [])

        for chunk_idx in range(0, len(messages), CHUNK_SIZE):
            chunk = messages[chunk_idx:chunk_idx + CHUNK_SIZE]

            status = f"Signal '{conv_name}': Nachrichten {chunk_idx+1}–{chunk_idx+len(chunk)}"
            if progress_callback:
                progress_callback(processed + 1, total_msgs, status)

            lines = []
            first_ts = 0
            senders = set()

            for msg in chunk:
                body = msg.get("body", "")
                if not body:
                    continue

                ts_ms = msg.get("timestamp", 0)
                ts = ts_ms // 1000 if ts_ms > 1e10 else ts_ms
                if not first_ts:
                    first_ts = ts

                sender = msg.get("author", msg.get("source", "Du"))
                senders.add(sender)

                dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M") if ts else "?"
                lines.append(f"[{dt_str}] {sender}: {body}")

            if not lines:
                continue

            doc_text = f"Signal Chat '{conv_name}':\n" + "\n".join(lines)

            try:
                embedding = embed_single(doc_text)
            except Exception as exc:
                logger.error("Embedding-Fehler: %s", exc)
                stats["errors"] += 1
                continue

            # Erwähnte Personen extrahieren
            from backend.ingestion.persons import extract_mentioned_persons
            try:
                mentioned = extract_mentioned_persons(doc_text, sender_names=list(senders))
            except Exception as exc:
                logger.warning("Personen-Extraktion fehlgeschlagen: %s", exc)
                mentioned = list(senders)

            chroma_meta = {
                "source": "signal",
                "chat_name": conv_name,
                "date_ts": first_ts,
                "date_iso": datetime.fromtimestamp(first_ts, tz=timezone.utc).isoformat() if first_ts else "",
                "lat": 0.0,
                "lon": 0.0,
                "persons": ",".join(senders),
                "mentioned_persons": ",".join(mentioned),
            }

            ids.append(f"signal_{conv_name[:20]}_{chunk_idx:05d}")
            documents.append(doc_text)
            embeddings.append(embedding)
            metadatas.append(chroma_meta)
            stats["success"] += len(lines)
            processed += len(chunk)

    if ids:
        upsert_documents_v2("messages", ids, documents, embeddings, metadatas)

    logger.info("Signal-Ingestion abgeschlossen: %s", stats)
    return stats
