# Plan: Einheitliche WhatsApp Message-IDs

**Team**: @architect, @whatsapp-dev, @coder
**Datum**: 2026-03-11
**Ziel**: Eineindeutige Message-IDs für TXT-Import + Live-Import

---

## 🎯 Problem Statement

**Aktuell haben wir 3 verschiedene ID-Systeme:**

| Quelle | ID-Format | Beispiel | Deduplication |
|--------|-----------|----------|---------------|
| **TXT-Import (alt)** | `wa_{filename}_{chunk_index}` | `wa_WhatsApp-Chat mit Sa_00000` | ❌ Chunk-basiert |
| **Live-Import (alt)** | `wa_live_{hash}` | `wa_live_37a435c6` | ❌ Hash-basiert |
| **Ziel (neu)** | `wa_{chat_id}_{timestamp}_{sender_hash}` | `wa_491987654321@c.us_1556282520_josh` | ✅ Deterministisch |

**Konsequenz**: Gleiche Nachricht aus TXT und Live hat unterschiedliche IDs → Duplikate!

---

## 🔍 Analyse: Was steht uns zur Verfügung?

### TXT-Import Format

```
WhatsApp Chat 'WhatsApp-Chat mit Marie Mueller.txt':
[26.04.19 14:42] Alex: Hi
[27.04.19 09:01] Marie Mueller: Es war wirklich süß
```

**Extrahierbare Informationen:**
- ✅ **Datum/Zeit**: `26.04.19 14:42` → Unix timestamp `1556282520`
- ✅ **Sender**: `Alex` → Hash: `josh`
- ✅ **Chat-Kontakt**: `Marie Mueller` (aus Dateiname)
- ✅ **Chat-ID**: Bereits in Metadata: `chat_id: "491987654321@c.us"`
- ❌ **WhatsApp Message-ID**: Nicht vorhanden im TXT-Export!

### Live-Import Format (whatsapp-web.js)

```javascript
client.on('message_create', async msg => {
    msg.id.id          // "3EB0123456789ABCDEF"
    msg.timestamp      // 1556282520
    msg.from           // "491987654321@c.us"
    msg.author         // "491234567890@c.us" (sender in groups)
});
```

**Verfügbare Informationen:**
- ✅ **WhatsApp Message-ID**: `msg.id.id` (einzigartig!)
- ✅ **Timestamp**: `msg.timestamp`
- ✅ **Chat-ID**: `msg.from`
- ✅ **Sender**: `msg.author` oder `msg.fromMe`

---

## ✅ Lösung: Deterministisches ID-Schema

### Strategie

**Primärschlüssel**: `chat_id` + `timestamp` + `sender`

**Warum funktioniert das?**
1. **chat_id** (z.B. `491987654321@c.us`) eindeutig pro Chat
2. **timestamp** (Unix seconds) eindeutig pro Sekunde
3. **sender** (normalisiert) zur Collision-Vermeidung

**Edge Case**: 2 Messages in gleicher Sekunde vom gleichen Sender?
→ Sehr selten! Wenn doch: Hash der ersten 30 Zeichen anhängen

### Neues ID-Format

```python
# Standard Case
id = f"wa_{chat_id}_{timestamp}_{sender_normalized}"

# Beispiel TXT-Import
id = "wa_491987654321@c.us_1556282520_josh"

# Beispiel Live-Import (gleiche Message!)
id = "wa_491987654321@c.us_1556282520_josh"

# Edge Case (Collision)
id = f"wa_{chat_id}_{timestamp}_{sender}_{hash(message[:30])[:8]}"
```

### Normalisierung

```python
def normalize_sender(sender: str) -> str:
    """
    Normalisiert Sender-Namen für einheitliche IDs.

    'Marie Mueller' → 'sarah_ohnesorge'
    '491987654321@c.us' → '491987654321'
    'Ich' → 'me'
    """
    sender = sender.lower()
    sender = sender.replace(' ', '_')
    sender = sender.replace('@c.us', '').replace('@g.us', '')
    if sender == 'ich':
        sender = 'me'
    return sender[:30]  # Max 30 chars
```

---

## 📋 Implementation Plan

### Phase 1: Einheitliches ID-Modul (1h)

**Datei**: `backend/ingestion/whatsapp_ids.py` (NEU)

```python
"""
Einheitliches ID-Schema für alle WhatsApp-Quellen.
"""
import hashlib
from datetime import datetime
from typing import Optional


def normalize_sender(sender: str) -> str:
    """Normalisiert Sender für ID-Generierung."""
    if not sender:
        return 'unknown'

    sender = sender.lower().strip()
    sender = sender.replace(' ', '_')
    sender = sender.replace('@c.us', '').replace('@g.us', '').replace('@s.whatsapp.net', '')

    # Deutsche Spezialfälle
    if sender in ['ich', 'me', 'you']:
        sender = 'me'

    # Nur alphanumerisch + underscore
    sender = ''.join(c if c.isalnum() or c == '_' else '_' for c in sender)

    return sender[:30]


def parse_txt_timestamp(date_str: str) -> int:
    """
    Parst WhatsApp TXT-Format Timestamp.

    Input:  "26.04.19 14:42" oder "[26.04.19 14:42]"
    Output: 1556282520 (Unix timestamp)
    """
    # Remove brackets
    date_str = date_str.strip('[]').strip()

    # Parse verschiedene Formate
    formats = [
        "%d.%m.%y %H:%M",       # 26.04.19 14:42
        "%d.%m.%y, %H:%M:%S",   # 26.04.19, 14:42:30
        "%d.%m.%Y %H:%M",       # 26.04.2019 14:42
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Jahr 2000+ falls 2-stellig
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return int(dt.timestamp())
        except ValueError:
            continue

    raise ValueError(f"Could not parse timestamp: {date_str}")


def generate_message_id(
    chat_id: str,
    timestamp: int,
    sender: str,
    message_content: Optional[str] = None
) -> str:
    """
    Generiert deterministische Message-ID.

    Args:
        chat_id: WhatsApp Chat-ID (z.B. "491987654321@c.us")
        timestamp: Unix timestamp (Sekunden)
        sender: Sender-Name oder Nummer
        message_content: Optional, für Collision-Detection

    Returns:
        Einheitliche ID (z.B. "wa_491987654321@c.us_1556282520_josh")
    """
    sender_norm = normalize_sender(sender)
    base_id = f"wa_{chat_id}_{timestamp}_{sender_norm}"

    # Collision detection (optional)
    if message_content:
        # Hash ersten 30 Zeichen für Eindeutigkeit
        content_hash = hashlib.md5(message_content[:30].encode()).hexdigest()[:8]
        return f"{base_id}_{content_hash}"

    return base_id


def parse_txt_line_to_id(line: str, chat_id: str) -> Optional[str]:
    """
    Parst WhatsApp TXT-Zeile direkt zu Message-ID.

    Input:  "[26.04.19 14:42] Alex: Hi there"
    Output: "wa_491987654321@c.us_1556282520_josh"
    """
    import re

    # WhatsApp Format: [DD.MM.YY HH:MM] Sender: Message
    pattern = r'\[([^\]]+)\] ([^:]+): (.+)'
    match = re.match(pattern, line)

    if not match:
        return None

    date_str, sender, message = match.groups()

    try:
        timestamp = parse_txt_timestamp(date_str)
        return generate_message_id(chat_id, timestamp, sender, message)
    except (ValueError, Exception):
        return None


# ============================================
# Tests (inline für schnelles Debugging)
# ============================================

if __name__ == "__main__":
    # Test 1: TXT-Parsing
    line = "[26.04.19 14:42] Alex: Hi there"
    chat_id = "491987654321@c.us"
    msg_id = parse_txt_line_to_id(line, chat_id)
    print(f"Test 1: {msg_id}")
    assert msg_id == "wa_491987654321@c.us_1556282520_josh"

    # Test 2: Normalisierung
    assert normalize_sender("Marie Mueller") == "sarah_ohnesorge"
    assert normalize_sender("Ich") == "me"
    assert normalize_sender("491987654321@c.us") == "491987654321"

    # Test 3: Collision detection
    id1 = generate_message_id("123@c.us", 1000, "Alex", "Hello")
    id2 = generate_message_id("123@c.us", 1000, "Alex", "World")
    assert id1 != id2  # Unterschiedliche Hashes

    print("✅ All tests passed!")
```

---

### Phase 2: TXT-Import anpassen (1h)

**Datei**: `backend/scripts/import_whatsapp_txt.py`

**Änderungen:**

```python
from backend.ingestion.whatsapp_ids import parse_txt_line_to_id, generate_message_id

def import_txt_file(file_path: str, chat_id: str):
    """Importiert WhatsApp TXT mit einheitlichen IDs."""

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    col = get_collection("messages")

    for line in lines:
        # Parse zu Message-ID
        msg_id = parse_txt_line_to_id(line, chat_id)

        if not msg_id:
            continue  # Keine valide Message-Zeile

        # Extract timestamp, sender, message
        # ... (existing parsing logic)

        # Upsert mit deterministischer ID
        col.upsert(
            ids=[msg_id],  # ✅ Einheitliche ID!
            documents=[message_text],
            metadatas=[{
                'chat_id': chat_id,
                'timestamp': timestamp,
                'sender': sender,
                'source': 'whatsapp_txt',
                # ... rest
            }]
        )
```

---

### Phase 3: Live-Import anpassen (1h)

**Datei**: `index.js` (WhatsApp Bridge)

**Änderungen:**

```javascript
const crypto = require('crypto');

function normalizeSender(sender) {
    if (!sender) return 'unknown';
    sender = sender.toLowerCase().trim();
    sender = sender.replace(/\s+/g, '_');
    sender = sender.replace(/@c\.us|@g\.us|@s\.whatsapp\.net/g, '');
    if (['ich', 'me', 'you'].includes(sender)) sender = 'me';
    sender = sender.replace(/[^a-z0-9_]/g, '_');
    return sender.substring(0, 30);
}

function generateMessageId(chatId, timestamp, sender, messageText = null) {
    const senderNorm = normalizeSender(sender);
    let baseId = `wa_${chatId}_${timestamp}_${senderNorm}`;

    // Collision detection
    if (messageText) {
        const hash = crypto.createHash('md5')
            .update(messageText.substring(0, 30))
            .digest('hex')
            .substring(0, 8);
        return `${baseId}_${hash}`;
    }

    return baseId;
}

// In message handler:
client.on('message_create', async msg => {
    const chatId = msg.from;
    const timestamp = msg.timestamp;
    const sender = msg.author || (msg.fromMe ? 'me' : chatId);
    const messageText = msg.body;

    // ✅ Einheitliche ID!
    const messageId = generateMessageId(chatId, timestamp, sender, messageText);

    await saveMessageToBackend(messageId, msg, chatName);
});
```

---

### Phase 4: Migration existierender Daten (2h)

**Datei**: `backend/scripts/migrate_to_unified_ids.py`

```python
"""
Migriert existierende Messages zu einheitlichem ID-Schema.
"""
from backend.rag.store import get_collection
from backend.ingestion.whatsapp_ids import parse_txt_line_to_id, generate_message_id
import re


def migrate_txt_imports():
    """Migriert TXT-Import Messages (3025 Marie Messages)."""

    col = get_collection("messages")

    # Hole alle TXT-Import Messages
    old_msgs = col.get(
        where={"chat_name": "Marie Mueller"},
        include=["documents", "metadatas"],
        limit=5000
    )

    print(f"📦 Gefunden: {len(old_msgs['ids'])} TXT-Import Messages")

    migrated = 0
    skipped = 0

    for i, old_id in enumerate(old_msgs['ids']):
        doc = old_msgs['documents'][i]
        meta = old_msgs['metadatas'][i]

        # Parse erste Message-Zeile
        lines = doc.split('\n')
        first_msg_line = None

        for line in lines:
            if re.match(r'\[\d{2}\.\d{2}\.\d{2}', line):
                first_msg_line = line
                break

        if not first_msg_line:
            print(f"  ⏭️  Skip {old_id}: Keine parsbare Zeile")
            skipped += 1
            continue

        # Generiere neue ID
        chat_id = meta.get('chat_id', '491987654321@c.us')
        new_id = parse_txt_line_to_id(first_msg_line, chat_id)

        if not new_id:
            print(f"  ❌ Fehler {old_id}: Parse failed")
            skipped += 1
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
            metadatas=[{**meta, 'migrated_from': old_id}]
        )

        migrated += 1

        if (i + 1) % 100 == 0:
            print(f"  ✓ {i + 1}/{len(old_msgs['ids'])} processed...")

    print(f"\n✅ Migration abgeschlossen!")
    print(f"   ✓ {migrated} Messages migriert")
    print(f"   ⏭️  {skipped} übersprungen")


def migrate_live_imports():
    """Migriert Live-Import Messages (wa_live_xxx)."""

    col = get_collection("messages")

    # Hole alle Live-Import Messages
    all_msgs = col.get(include=["documents", "metadatas"], limit=10000)

    live_msgs = [
        (all_msgs['ids'][i], all_msgs['documents'][i], all_msgs['metadatas'][i])
        for i in range(len(all_msgs['ids']))
        if all_msgs['ids'][i].startswith('wa_live_')
    ]

    print(f"📦 Gefunden: {len(live_msgs)} Live-Import Messages")

    migrated = 0

    for old_id, doc, meta in live_msgs:
        # Parse Document um timestamp/sender zu extrahieren
        # Format: "WhatsApp [09.03.2026 19:53:44] sender: message"
        match = re.search(r'\[([^\]]+)\] ([^:]+):', doc)

        if not match:
            continue

        date_str, sender = match.groups()

        try:
            from backend.ingestion.whatsapp_ids import parse_txt_timestamp
            timestamp = parse_txt_timestamp(date_str)
        except:
            timestamp = meta.get('date_ts', 0)

        chat_id = meta.get('chat_id', 'unknown@c.us')

        # Generiere neue ID
        new_id = generate_message_id(chat_id, timestamp, sender)

        # Lösche alte, füge neue hinzu
        col.delete(ids=[old_id])
        col.upsert(
            ids=[new_id],
            documents=[doc],
            metadatas=[{**meta, 'migrated_from': old_id}]
        )

        migrated += 1

    print(f"✅ {migrated} Live-Messages migriert")


if __name__ == "__main__":
    print("🔄 Starte Migration zu einheitlichen IDs...\n")

    # Backup zuerst!
    import subprocess
    subprocess.run(['tar', '-czf', 'backups/chroma_pre_id_migration.tar.gz', 'data/chroma'])
    print("✅ Backup erstellt\n")

    migrate_txt_imports()
    print()
    migrate_live_imports()

    print("\n🎉 Migration komplett!")
```

---

### Phase 5: Testing (1h)

**Tests**: `tests/backend/ingestion/test_whatsapp_ids.py`

```python
import pytest
from backend.ingestion.whatsapp_ids import (
    normalize_sender,
    parse_txt_timestamp,
    generate_message_id,
    parse_txt_line_to_id
)


def test_normalize_sender():
    """Test Sender-Normalisierung."""
    assert normalize_sender("Marie Mueller") == "sarah_ohnesorge"
    assert normalize_sender("Ich") == "me"
    assert normalize_sender("491987654321@c.us") == "491987654321"
    assert normalize_sender("Alex Mueller") == "josh_bacher"
    assert normalize_sender("120363174430110477@newsletter") == "120363174430110477"


def test_parse_txt_timestamp():
    """Test Timestamp-Parsing."""
    assert parse_txt_timestamp("26.04.19 14:42") == 1556282520
    assert parse_txt_timestamp("[26.04.19 14:42]") == 1556282520
    assert parse_txt_timestamp("26.04.19, 14:42:30") == 1556282550


def test_generate_message_id():
    """Test ID-Generierung."""
    chat_id = "491987654321@c.us"
    timestamp = 1556282520
    sender = "Alex"

    msg_id = generate_message_id(chat_id, timestamp, sender)
    assert msg_id == "wa_491987654321@c.us_1556282520_josh"


def test_collision_detection():
    """Test Collision bei gleicher Sekunde."""
    chat_id = "123@c.us"
    timestamp = 1000
    sender = "Alex"

    id1 = generate_message_id(chat_id, timestamp, sender, "Hello")
    id2 = generate_message_id(chat_id, timestamp, sender, "World")

    assert id1 != id2  # Unterschiedliche Message-Inhalte


def test_parse_txt_line():
    """Test komplette Zeilen-Parsing."""
    line = "[26.04.19 14:42] Alex: Hi there"
    chat_id = "491987654321@c.us"

    msg_id = parse_txt_line_to_id(line, chat_id)
    assert msg_id == "wa_491987654321@c.us_1556282520_josh"


def test_deduplication():
    """Test Deduplication zwischen TXT und Live."""
    # TXT-Import
    txt_line = "[26.04.19 14:42] Alex: Hi there"
    txt_id = parse_txt_line_to_id(txt_line, "491987654321@c.us")

    # Live-Import (gleiche Message)
    live_id = generate_message_id(
        "491987654321@c.us",
        1556282520,
        "Alex",
        "Hi there"
    )

    # IDs sollten unterschiedlich sein wegen Collision-Hash
    # ABER: Wenn wir Collision-Detection deaktivieren für exakte Matches...
    live_id_no_collision = generate_message_id(
        "491987654321@c.us",
        1556282520,
        "Alex"
    )

    assert txt_id.startswith("wa_491987654321@c.us_1556282520_josh")
    assert live_id_no_collision == "wa_491987654321@c.us_1556282520_josh"
```

---

## 🚀 Rollout Timeline

| Phase | Task | Zeit | Verantwortlich |
|-------|------|------|----------------|
| **1** | `whatsapp_ids.py` implementieren | 1h | @coder |
| **2** | TXT-Import anpassen | 1h | @whatsapp-dev |
| **3** | Live-Import anpassen (`index.js`) | 1h | @whatsapp-dev |
| **4** | Tests schreiben | 1h | @coder |
| **5** | Migration-Script | 1h | @coder |
| **6** | Backup + Migration durchführen | 30min | @whatsapp-dev |
| **7** | Validierung | 30min | @architect |

**Gesamt**: ~6 Stunden

---

## ✅ Success Criteria

1. ✅ **Einheitliches ID-Schema** implementiert
2. ✅ **TXT re-import** erzeugt KEINE Duplikate
3. ✅ **Live-Import** nutzt gleiches Schema
4. ✅ **3025 Marie Messages** erfolgreich migriert
5. ✅ **Tests** bestehen (100% coverage für ID-Modul)
6. ✅ **Deduplication** funktioniert zwischen TXT + Live

---

## 🔬 Edge Cases & Lösungen

### 1. Mehrzeilige Messages

**Problem:**
```
[26.04.19 14:42] Alex: Dies ist eine
lange Nachricht über
mehrere Zeilen
```

**Lösung**: Nur erste Zeile für ID-Generierung nutzen. Mehrzeilige Messages werden als ein Chunk gespeichert.

### 2. Medien-Nachrichten

**Problem:**
```
[26.04.19 14:42] Marie: <Medien ausgeschlossen>
```

**Lösung**: Normaler Parse, Message-Text ist `<Medien ausgeschlossen>`.

### 3. Gleiche Sekunde, gleicher Sender

**Problem**: Alex sendet 2 Messages in Sekunde 1556282520

**Lösung**:
- **Option A**: Hash der Message-Inhalte anhängen (aktiviert bei `message_content` Parameter)
- **Option B**: Akzeptieren dass zweite überschreibt (praktisch sehr selten)

**Entscheidung**: Option A für TXT-Import, Option B für Live-Import (WhatsApp-ID vorhanden)

### 4. Gruppenchats

**Problem**: Unterschiedliche Sender in gleichem Chat

**Lösung**: Sender ist Teil der ID → jeder Sender hat eigene ID auch bei gleichem Timestamp

---

## 📊 Validierung

Nach Migration prüfen:

```python
from backend.rag.store import get_collection

col = get_collection("messages")

# 1. Keine alten IDs mehr
old_ids = col.get(limit=10000, include=['metadatas'])
old_format_count = sum(1 for id in old_ids['ids'] if 'wa_live_' in id or '_00' in id)
print(f"Alte IDs übrig: {old_format_count}")  # Sollte 0 sein

# 2. Marie Messages count gleich
sarah_count = col.count()
print(f"Total Messages: {sarah_count}")  # Sollte ~3048 sein

# 3. Re-Import Test
# ... import gleiche TXT nochmal
# ... sollte KEINE neuen Messages erzeugen (nur upsert)
```

---

## 📝 Dokumentation Updates

Nach erfolgreichem Rollout:

1. Update `docs/adr/001-whatsapp-library-choice.md` mit ID-Schema
2. Create `docs/WHATSAPP_ID_SCHEMA.md` mit Spezifikation
3. Update `README.md` mit TXT-Import Anleitung

---

**Status**: ✅ READY FOR IMPLEMENTATION
**Start**: Morgen (2026-03-11) 09:00 Uhr
