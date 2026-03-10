#!/usr/bin/env python3
"""
Migration Script: Alte IDs → Einheitliche WhatsApp-IDs

Migriert existierende Messages (TXT-Import + Live-Import) zum neuen ID-Schema:
- Alt:  wa_WhatsApp-Chat mit Sa_00000
- Alt:  wa_live_37a435c6
- Neu:  wa_491786838260@c.us_1556282520_josh

WICHTIG: Backup vor Ausführung!
"""
import re
import sys
from datetime import datetime
from backend.rag.store import get_collection
from backend.ingestion.whatsapp_ids import parse_txt_line_to_id, generate_message_id, parse_txt_line


def create_backup():
    """Erstellt Backup von ChromaDB."""
    import subprocess
    import os

    os.makedirs('backups', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f'backups/chroma_pre_id_migration_{timestamp}.tar.gz'

    print(f"📦 Erstelle Backup: {backup_file}")
    result = subprocess.run(
        ['tar', '-czf', backup_file, 'data/chroma'],
        capture_output=True
    )

    if result.returncode == 0:
        # Get file size
        size_mb = os.path.getsize(backup_file) / (1024 * 1024)
        print(f"✅ Backup erstellt: {backup_file} ({size_mb:.1f} MB)")
        return backup_file
    else:
        print(f"❌ Backup failed: {result.stderr.decode()}")
        sys.exit(1)


def migrate_txt_imports():
    """Migriert TXT-Import Messages zu einheitlichen IDs."""

    print("\n🔄 Migriere TXT-Import Messages...")

    col = get_collection("messages")

    # Hole alle Messages (begrenzt, aber sollte reichen)
    all_msgs = col.get(include=["documents", "metadatas"], limit=10000)

    # Filter für TXT-Imports (alte ID-Format)
    txt_msgs = [
        (all_msgs['ids'][i], all_msgs['documents'][i], all_msgs['metadatas'][i])
        for i in range(len(all_msgs['ids']))
        if '_00' in all_msgs['ids'][i] or 'WhatsApp-Chat' in all_msgs['ids'][i]
    ]

    print(f"📦 Gefunden: {len(txt_msgs)} TXT-Import Messages")

    if len(txt_msgs) == 0:
        print("ℹ️  Keine TXT-Import Messages zum Migrieren")
        return

    migrated = 0
    skipped = 0
    errors = 0

    for old_id, doc, meta in txt_msgs:
        try:
            # Parse erste Message-Zeile aus Document
            lines = doc.split('\n')
            first_msg_line = None

            for line in lines:
                # WhatsApp Format: [DD.MM.YY HH:MM] Sender: Message
                if re.match(r'\[\d{2}\.\d{2}\.\d{2}', line):
                    first_msg_line = line
                    break

            if not first_msg_line:
                print(f"  ⏭️  Skip {old_id[:50]}: Keine parsbare Zeile")
                skipped += 1
                continue

            # Generiere neue ID
            chat_id = meta.get('chat_id', 'unknown@c.us')
            new_id = parse_txt_line_to_id(first_msg_line, chat_id)

            if not new_id:
                print(f"  ❌ Fehler {old_id[:50]}: Parse failed")
                errors += 1
                continue

            # Nur migrieren wenn ID unterschiedlich
            if new_id == old_id:
                skipped += 1
                continue

            # Lösche alte ID, füge neue hinzu
            col.delete(ids=[old_id])
            col.upsert(
                ids=[new_id],
                documents=[doc],
                metadatas=[{**meta, 'migrated_from': old_id, 'migrated_at': datetime.now().isoformat()}]
            )

            migrated += 1

            if migrated % 100 == 0:
                print(f"  ✓ {migrated} Messages migriert...")

        except Exception as e:
            print(f"  ❌ Fehler bei {old_id[:50]}: {e}")
            errors += 1
            continue

    print(f"\n✅ TXT-Import Migration abgeschlossen!")
    print(f"   ✓ {migrated} Messages migriert")
    print(f"   ⏭️  {skipped} übersprungen")
    print(f"   ❌ {errors} Fehler")


def migrate_live_imports():
    """Migriert Live-Import Messages zu einheitlichen IDs."""

    print("\n🔄 Migriere Live-Import Messages...")

    col = get_collection("messages")

    # Hole alle Messages
    all_msgs = col.get(include=["documents", "metadatas"], limit=10000)

    # Filter für Live-Imports (wa_live_xxx)
    live_msgs = [
        (all_msgs['ids'][i], all_msgs['documents'][i], all_msgs['metadatas'][i])
        for i in range(len(all_msgs['ids']))
        if all_msgs['ids'][i].startswith('wa_live_')
    ]

    print(f"📦 Gefunden: {len(live_msgs)} Live-Import Messages")

    if len(live_msgs) == 0:
        print("ℹ️  Keine Live-Import Messages zum Migrieren")
        return

    migrated = 0
    errors = 0

    for old_id, doc, meta in live_msgs:
        try:
            # Parse Document um timestamp/sender zu extrahieren
            # Format: "WhatsApp [09.03.2026 19:53:44] sender: message"
            match = re.search(r'\[([^\]]+)\]\s*([^:]+):', doc)

            if not match:
                print(f"  ⏭️  Skip {old_id}: Kann nicht parsen")
                continue

            date_str, sender = match.groups()

            # Parse timestamp aus date_str
            parsed = parse_txt_line(f"[{date_str}] {sender}: dummy")
            if not parsed:
                # Fallback zu metadata
                timestamp = meta.get('date_ts', 0)
            else:
                timestamp = parsed['timestamp']

            chat_id = meta.get('chat_id', 'unknown@c.us')

            # Generiere neue ID
            new_id = generate_message_id(chat_id, timestamp, sender)

            # Lösche alte, füge neue hinzu
            col.delete(ids=[old_id])
            col.upsert(
                ids=[new_id],
                documents=[doc],
                metadatas=[{**meta, 'migrated_from': old_id, 'migrated_at': datetime.now().isoformat()}]
            )

            migrated += 1

        except Exception as e:
            print(f"  ❌ Fehler bei {old_id}: {e}")
            errors += 1
            continue

    print(f"\n✅ Live-Import Migration abgeschlossen!")
    print(f"   ✓ {migrated} Messages migriert")
    print(f"   ❌ {errors} Fehler")


def validate_migration():
    """Validiert dass Migration erfolgreich war."""

    print("\n🔍 Validiere Migration...")

    col = get_collection("messages")

    # Hole alle IDs
    all_msgs = col.get(limit=10000)

    # Zähle alte ID-Formate
    old_txt_count = sum(1 for id in all_msgs['ids'] if '_00' in id or 'WhatsApp-Chat' in id)
    old_live_count = sum(1 for id in all_msgs['ids'] if id.startswith('wa_live_'))

    # Zähle neue ID-Formate
    new_count = sum(1 for id in all_msgs['ids'] if id.startswith('wa_') and '@' in id and not id.startswith('wa_live_'))

    print(f"\n📊 Validierungs-Ergebnisse:")
    print(f"   Total Messages: {len(all_msgs['ids'])}")
    print(f"   Alte TXT-IDs übrig: {old_txt_count}")
    print(f"   Alte Live-IDs übrig: {old_live_count}")
    print(f"   Neue einheitliche IDs: {new_count}")

    if old_txt_count == 0 and old_live_count == 0:
        print("\n✅ Migration erfolgreich! Keine alten IDs mehr vorhanden.")
        return True
    else:
        print("\n⚠️  Warnung: Noch alte IDs vorhanden!")
        return False


def main():
    """Haupt-Migrations-Funktion."""

    print("=" * 60)
    print("🔄 WhatsApp Message ID Migration")
    print("=" * 60)

    # Confirmation
    print("\n⚠️  WARNUNG: Diese Migration ändert alle Message-IDs!")
    print("   Backup wird automatisch erstellt.")
    response = input("\nFortfahren? (ja/nein): ")

    if response.lower() not in ['ja', 'j', 'yes', 'y']:
        print("❌ Migration abgebrochen")
        sys.exit(0)

    # Backup
    backup_file = create_backup()

    # Migration
    migrate_txt_imports()
    migrate_live_imports()

    # Validation
    validate_migration()

    print("\n" + "=" * 60)
    print("🎉 Migration abgeschlossen!")
    print(f"📦 Backup: {backup_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
