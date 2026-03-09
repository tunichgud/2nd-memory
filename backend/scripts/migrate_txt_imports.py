#!/usr/bin/env python3
"""
Migration Script: TXT-Import → WhatsApp Live Format

Strategie: Metadaten-Anreicherung
- Behält die Chunking-Struktur (gut für RAG-Kontext)
- Aktualisiert chat_name: "WhatsApp-Chat mit Sarah.txt" → "Sarah Ohnesorge"
- Fügt fehlende Metadaten hinzu (sender, timestamp, etc.)
- Behält alle existierenden Metadaten (persons, mentioned_persons, etc.)
"""

from backend.rag.store import get_collection
from datetime import datetime
import re


def migrate_txt_chat(old_chat_name: str, new_chat_name: str, phone: str = None):
    """
    Migriert einen TXT-Import-Chat zu WhatsApp Live-Format.

    Args:
        old_chat_name: z.B. "WhatsApp-Chat mit Sarah Ohnesorge.txt"
        new_chat_name: z.B. "Sarah Ohnesorge"
        phone: Optional WhatsApp-Nummer (z.B. "491786838260")
    """
    print(f"🔄 Migriere: {old_chat_name} → {new_chat_name}")

    col = get_collection("messages")

    # Hole alle Nachrichten des Chats
    results = col.get(
        where={"chat_name": old_chat_name},
        include=["documents", "metadatas"]
    )

    if not results["ids"]:
        print(f"❌ Keine Nachrichten gefunden für: {old_chat_name}")
        return

    print(f"📦 Gefunden: {len(results['ids'])} Chunks")

    # Parse erste Nachricht um Chat-ID zu bestimmen
    chat_id = f"{phone}@c.us" if phone else "unknown@c.us"

    migrated = 0
    errors = 0

    for i, msg_id in enumerate(results["ids"]):
        try:
            old_meta = results["metadatas"][i]
            document = results["documents"][i]

            # Erstelle neue Metadaten
            new_meta = {
                **old_meta,  # Behalte alle existierenden Metadaten
                "chat_id": chat_id,
                "chat_name": new_chat_name,  # ← Hauptänderung
                "migration_source": "txt_import",
                "migration_date": datetime.now().isoformat(),
            }

            # Extrahiere ersten Sender aus dem Chunk (falls vorhanden)
            sender_match = re.search(r'\] ([^:]+):', document)
            if sender_match:
                new_meta["primary_sender"] = sender_match.group(1)

            # Timestamp bereits vorhanden als date_ts
            if "date_ts" in old_meta and old_meta["date_ts"]:
                ts = datetime.fromtimestamp(old_meta["date_ts"])
                new_meta["timestamp"] = ts.isoformat()

            # Update in ChromaDB
            col.upsert(
                ids=[msg_id],
                documents=[document],
                metadatas=[new_meta]
            )

            migrated += 1

            if (i + 1) % 10 == 0:
                print(f"  ✓ {i + 1}/{len(results['ids'])} Chunks migriert...")

        except Exception as e:
            print(f"  ❌ Fehler bei {msg_id}: {e}")
            errors += 1

    print(f"✅ Migration abgeschlossen!")
    print(f"   ✓ {migrated} Chunks migriert")
    if errors > 0:
        print(f"   ❌ {errors} Fehler")
    print()


def list_txt_imports():
    """Zeigt alle TXT-Import-Chats"""
    col = get_collection("messages")

    all_msgs = col.get(limit=10000, include=["metadatas"])

    # Finde alle Chats mit .txt Endung
    txt_chats = {}
    for meta in all_msgs["metadatas"]:
        chat_name = meta.get("chat_name", "")
        if ".txt" in chat_name:
            txt_chats[chat_name] = txt_chats.get(chat_name, 0) + 1

    print("📋 Gefundene TXT-Imports:")
    print("="*60)
    for chat, count in sorted(txt_chats.items()):
        print(f"  - {chat}: {count} Chunks")
    print()

    return list(txt_chats.keys())


if __name__ == "__main__":
    print("🦕 WhatsApp TXT-Import Migration Tool")
    print("="*60)
    print()

    # Liste alle TXT-Imports
    txt_chats = list_txt_imports()

    if not txt_chats:
        print("✅ Keine TXT-Imports gefunden - nichts zu migrieren")
        exit(0)

    # Migriere Sarah's Chat
    print("📝 Migration starten...")
    print()

    # Mapping: alter Name → neuer Name + Telefonnummer
    migrations = [
        {
            "old": "WhatsApp-Chat mit Sarah Ohnesorge.txt",
            "new": "Sarah Ohnesorge",
            "phone": "491786838260"  # aus /api/whatsapp/chats
        },
        # Weitere Migrationen hier hinzufügen...
    ]

    for migration in migrations:
        if migration["old"] in txt_chats:
            migrate_txt_chat(
                migration["old"],
                migration["new"],
                migration["phone"]
            )
        else:
            print(f"⏭️  Überspringe: {migration['old']} (nicht gefunden)")
            print()

    print("🎉 Alle Migrationen abgeschlossen!")
