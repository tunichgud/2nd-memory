# TODO: TXT-Import Deduplication mit WhatsApp Live-IDs

**Status**: Planned
**Priority**: High
**Assignee**: @whatsapp-dev, @coder

## Problem

Aktuell haben wir **zwei separate ID-Systeme**:

1. **TXT-Import**: `wa_WhatsApp-Chat mit Sa_00000` (chunk-basiert)
2. **Live-Import**: `wa_CHATID_MSGID_TIMESTAMP` (message-basiert)

→ **Ergebnis**: Semantische Duplikate möglich (gleiche Nachricht, unterschiedliche IDs)

## Ziel

**Einheitliches ID-System** für alle WhatsApp-Messages, egal ob aus TXT oder Live-Import.

## Lösung: WhatsApp Message-ID aus TXT extrahieren

### Strategie

WhatsApp TXT-Exports enthalten **implizite Informationen** zur Deduplizierung:

```
[09.03.26, 23:15:42] Marie: Hallo Alex!
[09.03.26, 23:16:10] Ich: Hey Marie!
```

**Extrahierbare Daten**:
- ✅ Timestamp: `09.03.26, 23:15:42` → Unix timestamp
- ✅ Sender: `Marie` / `Ich`
- ✅ Chat Name: Aus Dateinamen

**Generierbare ID**:
```python
# Statt chunk-basiert:
id = f"wa_{chat_name}_{chunk_index}"

# Besser: timestamp + sender basiert
id = f"wa_{chat_id}_{unix_timestamp}_{sender_hash}"
```

### Implementation Plan

#### Phase 1: TXT Parser erweitern

**Datei**: `backend/ingestion/txt_parser.py` (neu erstellen)

```python
import re
from datetime import datetime

def parse_whatsapp_txt_line(line: str, chat_id: str):
    """
    Parst WhatsApp TXT-Zeile und erstellt eindeutige ID.

    Input:  "[09.03.26, 23:15:42] Marie: Hallo Alex!"
    Output: {
        'id': 'wa_491987654321@c.us_1741562142_sarah',
        'timestamp': 1741562142,
        'sender': 'Marie',
        'message': 'Hallo Alex!'
    }
    """
    # Regex für WhatsApp Format
    pattern = r'\[(\d{2}\.\d{2}\.\d{2}), (\d{2}:\d{2}:\d{2})\] ([^:]+): (.+)'
    match = re.match(pattern, line)

    if not match:
        return None

    date_str, time_str, sender, message = match.groups()

    # Parse timestamp
    dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M:%S")
    unix_ts = int(dt.timestamp())

    # Generiere eindeutige ID
    sender_clean = sender.lower().replace(' ', '_')
    msg_id = f"wa_{chat_id}_{unix_ts}_{sender_clean}"

    return {
        'id': msg_id,
        'timestamp': unix_ts,
        'sender': sender,
        'message': message
    }
```

#### Phase 2: Import-Script anpassen

**Datei**: `backend/scripts/import_whatsapp_txt.py`

**Vor** (chunk-basiert):
```python
for i, chunk in enumerate(chunks):
    msg_id = f"wa_{chat_name}_{i:05d}"  # ❌ Chunk-Index
    col.upsert(ids=[msg_id], ...)
```

**Nach** (message-basiert):
```python
for line in txt_lines:
    parsed = parse_whatsapp_txt_line(line, chat_id)
    if parsed:
        msg_id = parsed['id']  # ✅ Timestamp + Sender
        col.upsert(ids=[msg_id], ...)
```

#### Phase 3: Migration existierender Daten

**Datei**: `backend/scripts/migrate_txt_to_proper_ids.py`

```python
def migrate_sarah_txt_imports():
    """
    Migriert die 3025 Marie TXT-Import Messages zu korrekten IDs.
    """
    col = get_collection("messages")

    # Hole alle TXT-Import Messages
    old_msgs = col.get(
        where={"chat_name": "Marie Mueller", "source": "whatsapp"},
        include=["documents", "metadatas"]
    )

    for i, old_id in enumerate(old_msgs['ids']):
        doc = old_msgs['documents'][i]
        meta = old_msgs['metadatas'][i]

        # Parse erste Zeile um timestamp/sender zu extrahieren
        parsed = parse_whatsapp_txt_line(doc.split('\n')[0], "491987654321@c.us")

        if parsed:
            new_id = parsed['id']

            # Lösche alte ID, füge neue hinzu
            col.delete(ids=[old_id])
            col.upsert(
                ids=[new_id],
                documents=[doc],
                metadatas=[{**meta, 'timestamp': parsed['timestamp']}]
            )
```

### Edge Cases

1. **Mehrzeilige Messages**
   ```
   [09.03.26, 23:15:42] Marie: Hallo Alex!
   Das ist eine lange
   Nachricht über mehrere Zeilen
   ```
   → Nur erste Zeile parsen, Rest als continuation

2. **Medien-Messages**
   ```
   [09.03.26, 23:15:42] Marie: <Medien ausgeschlossen>
   ```
   → Spezial-Handling für Platzhalter

3. **Identische Timestamps** (2 Messages in gleicher Sekunde)
   ```
   [09.03.26, 23:15:42] Marie: Hi!
   [09.03.26, 23:15:42] Ich: Hey!
   ```
   → ID erweitern: `wa_{chat_id}_{timestamp}_{sender}_{hash(message[:20])}`

### Testing Plan

1. **Unit Tests**: `tests/backend/ingestion/test_txt_parser.py`
   - Parse verschiedene WhatsApp TXT-Formate
   - Edge Cases (mehrzeilig, Medien, etc.)

2. **Integration Test**:
   - Import kleiner TXT-Datei
   - Re-Import gleicher Datei → KEINE Duplikate!
   - Live-Import gleicher Nachricht → Überschreibt TXT-Import

3. **Migration Test**:
   - Backup ChromaDB
   - Migrate 3025 Marie Messages
   - Verify: Keine Duplikate, korrekte IDs

### Rollout Plan

**Phase A**: Implementation (1-2h)
1. Create `backend/ingestion/txt_parser.py`
2. Update `backend/scripts/import_whatsapp_txt.py`
3. Write tests

**Phase B**: Migration (30min)
1. Backup ChromaDB
2. Run migration script
3. Verify results

**Phase C**: Validation (30min)
1. Test re-import von Marie TXT
2. Test Live-Import von Marie Messages
3. Query RAG: "Was weißt du über Marie?"

## Success Criteria

✅ TXT-Import generiert IDs: `wa_{chat_id}_{timestamp}_{sender}`
✅ Re-Import TXT → KEINE Duplikate
✅ Live-Import + TXT-Import → automatische Deduplication
✅ 3025 Marie Messages migriert zu neuen IDs
✅ RAG funktioniert weiterhin korrekt

## Open Questions

1. **Chunking beibehalten?**
   - TXT-Import chunked für besseren RAG-Kontext
   - Live-Import einzelne Messages
   - **Lösung**: Beide Formate parallel OK, aber eindeutige IDs!

2. **Was bei timestamp collisions?**
   - Sehr selten (gleiche Sekunde)
   - **Lösung**: Hash der ersten 20 Zeichen anhängen

3. **Backwards compatibility?**
   - Alte IDs (`wa_WhatsApp-Chat mit Sa_00000`) bleiben in DB
   - **Lösung**: Migration-Script löscht alte, erstellt neue IDs

## Resources

- WhatsApp TXT Format Docs: https://faq.whatsapp.com/1180414079177245
- Regex Tester: https://regex101.com/
- ChromaDB Upsert Docs: https://docs.trychroma.com/reference/Collection#upsert

## Timeline

**Morgen (2026-03-11)**:
- 09:00-11:00: Implementation
- 11:00-11:30: Testing
- 11:30-12:00: Migration Marie Data
- 12:00-12:30: Validation & Documentation

---

**Notes**: Diese TODO wird morgen abgearbeitet zusammen mit @whatsapp-dev und @coder.
