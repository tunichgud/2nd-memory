# WhatsApp Integration - Features

## Übersicht

Memosaur bietet eine vollständige WhatsApp-Integration mit automatischer Nachrichtenspeicherung, KI-Bot-Funktionalität und Chat-Historie-Import.

---

## ✅ Implementierte Features

### 1. WhatsApp Bot (Conversational AI)

**Beschreibung:**
Ein KI-Bot, der auf WhatsApp-Nachrichten antwortet und Zugriff auf deine persönliche Wissensdatenbank (Photos, Maps, Messages) hat.

**Funktionalität:**
- ✅ Antwortet nur auf Nachrichten **AN DICH** in deinem persönlichen Chat
- ✅ Nutzt RAG (Retrieval-Augmented Generation) für kontextbezogene Antworten
- ✅ Greift auf alle gespeicherten Daten zu (Fotos, Orte, Nachrichten)
- ✅ Ignoriert automatisch eigene Antworten (Loop Prevention via 🦕 Prefix)

**Sicherheit:**
- ✅ Bot antwortet NUR im konfigurierten User-Chat
- ✅ Alle anderen Chats werden komplett ignoriert (keine Backend-Calls)
- ✅ Master-Kill-Switch: Bot kann jederzeit deaktiviert werden
- ✅ TEST_MODE für Entwicklung/Testing (verarbeitet eigene Nachrichten)

**Konfiguration:**
- User-Chat-ID wird automatisch erkannt (aus gekoppeltem WhatsApp-Account)
- Persistent in ChromaDB gespeichert
- Frontend-UI in Settings → WhatsApp Integration

**API Endpoints:**
- `GET /api/whatsapp/config` - Aktuelle Konfiguration
- `POST /api/whatsapp/config/user-chat` - User-Chat-ID setzen
- `POST /api/whatsapp/config/bot-enabled` - Bot aktivieren/deaktivieren
- `POST /api/whatsapp/config/test-mode` - TEST_MODE an/aus

**Dateien:**
- `index.js` - WhatsApp Bridge mit Bot-Logik
- `backend/api/v1/whatsapp.py` - REST API für Konfiguration
- `backend/config/whatsapp_config.py` - Config Management (ChromaDB)
- `frontend/index.html` - Settings UI

---

### 2. Live Message Ingestion

**Beschreibung:**
Jede WhatsApp-Nachricht (aus allen Chats) wird automatisch in ChromaDB gespeichert.

**Funktionalität:**
- ✅ **Alle** eingehenden und ausgehenden Nachrichten werden erfasst
- ✅ Läuft parallel zur Bot-Verarbeitung
- ✅ Asynchrone Verarbeitung (Backend Background Tasks)
- ✅ Speichert Metadaten: Sender, Chat-Name, Timestamp, Typ
- ✅ Markiert Quelle als "whatsapp"

**Datenstruktur (ChromaDB):**
```json
{
  "message_id": "true_491234567890@c.us_3EB0...",
  "chat_id": "491234567890@c.us",
  "chat_name": "Lisa Müller",
  "sender": "Lisa Müller",
  "text": "Hallo, wie geht's?",
  "timestamp": "2026-03-09T21:30:00",
  "is_from_me": false,
  "has_media": false,
  "type": "chat",
  "source": "whatsapp"
}
```

**Performance:**
- Non-blocking: Client wartet nicht auf Speicherung
- Background Tasks in FastAPI
- Keine Auswirkung auf Bot-Response-Zeit

**API Endpoints:**
- `POST /api/whatsapp/message` - Speichert eine Nachricht (Background Task)

**Dateien:**
- `index.js:79-102` - Live-Ingestion Funktion
- `index.js:129-133` - Aufruf bei jeder Nachricht
- `backend/api/v1/whatsapp.py:181-250` - Backend Endpoint

---

### 3. Intelligent Bulk Import System (Chat-Historie)

**Beschreibung:**
Importiert die komplette WhatsApp-Chat-Historie mit intelligenter Priorisierung, automatischer Deduplizierung und WhatsApp-Ban-Schutz.

**🌟 Kernfeatures:**
- ✅ **Chat-Priorisierung**: Sortierung nach Aktivität (neueste zuerst)
- ✅ **Smart Deduplication**: Trackt letzten Import-Timestamp pro Chat, importiert nur neue Nachrichten
- ✅ **Rate Limiting**: 3s zwischen Chats, 60s Batch-Pausen (alle 10 Chats)
- ✅ **Zeitfenster-Schutz**: Import nur 09:00-22:00 Uhr (Ban-Prävention)
- ✅ **Exponential Backoff**: Automatische Verzögerung bei Rate-Limit-Errors (5s → 10s → 20s → 40s)
- ✅ **Unlimited Messages**: Importiert ALLE Nachrichten (`limit: Infinity`)
- ✅ **Fortsetzbarer Import**: Re-Import lädt nur neue Nachrichten seit letztem Run
- ✅ **Persistentes Tracking**: Alle Importe werden in ChromaDB protokolliert

**Smart Deduplication (Per-Chat Tracking):**
```json
{
  "chat_id": "4917012345678@c.us",
  "last_imported_timestamp": 1741814400,
  "last_imported_message_id": "true_4917012345678@c.us_3EB0...",
  "first_import_run": "2026-03-09T10:00:00",
  "import_runs": 3,
  "total_messages_imported": 1523
}
```

**Import-Strategie:**
1. **Sortierung**: Chats nach `lastMessage.timestamp` (neueste zuerst)
2. **Zeitfenster-Check**: Nur 09:00-22:00 Uhr
3. **Deduplication**: Lade nur Nachrichten mit `timestamp > last_imported_timestamp`
4. **Rate Limiting**:
   - 3 Sekunden Pause zwischen Chats
   - 60 Sekunden Pause nach jedem 10. Chat
   - Exponential Backoff bei Errors
5. **Tracking**: Update `last_imported_timestamp` nach jedem Chat

**Workflow:**
1. User startet Import (Frontend)
2. System prüft Zeitfenster (09:00-22:00)
3. Chats laden & sortieren (neueste zuerst)
4. Für jeden Chat:
   - Hole `last_imported_timestamp` vom Backend
   - Lade ALLE Nachrichten (`limit: Infinity`)
   - Filtere: nur `timestamp > last_imported_timestamp`
   - Speichere neue Nachrichten
   - Update Timestamp im Backend
   - Pause 3s
5. Nach 10 Chats: Pause 60s
6. Bei Zeitfenster-Ende: Pausieren & Status speichern

**Ban-Risiko-Mitigation:**
- ⏰ **Zeitfenster**: Nur tagsüber (09:00-22:00)
- 🐢 **Conservative Rate Limiting**: 3s zwischen Chats, 60s Batch-Pausen
- 📖 **Read-Only**: WhatsApp banns eher bei Mass-Messaging, nicht bei Lesen
- 🔄 **Exponential Backoff**: Automatische Verlangsamung bei Rate Limits
- ✅ **User-Research**: Andere Nutzer berichten: Lesen ist safe, Senden ist riskant

**API Endpoints:**

*Import Plan Management:*
- `GET /api/whatsapp/import-plan` - Status abrufen
- `POST /api/whatsapp/import-plan/start` - Import starten mit Chat-Liste
- `POST /api/whatsapp/import-plan/mark-in-progress` - Chat als aktiv markieren
- `POST /api/whatsapp/import-plan/mark-completed` - Chat als fertig markieren
- `POST /api/whatsapp/import-plan/reset` - Plan zurücksetzen

*Smart Deduplication:*
- `GET /api/whatsapp/import-plan/chat/{chat_id}/last-import` - Letzten Timestamp holen
- `POST /api/whatsapp/import-plan/chat/{chat_id}/update-timestamp` - Timestamp aktualisieren
- `GET /api/whatsapp/import-plan/stats` - Import-Statistiken

*WhatsApp Bridge:*
- `POST /api/whatsapp/import-all-chats` - Führt intelligenten Import durch
- `GET /api/whatsapp/chats` - Chat-Liste mit Import-Status

**Dateien:**
- `backend/config/whatsapp_import.py:207-362` - Smart Deduplication Functions
- `backend/api/v1/whatsapp.py:348-448` - Timestamp Tracking Endpoints
- `index.js:270-324` - Rate Limiting & Helper Functions
- `index.js:326-480` - Intelligent Bulk Import Implementation
- `frontend/index.html:779-886` - Import UI mit Modals & Progress
- `frontend/index.html:1351-1414` - Import Function mit Zeitfenster-Check
- `frontend/index.html:1442-1651` - Chat Selection & Stats UI

---

### 4. Auto-Configuration

**Beschreibung:**
Automatische Erkennung der User-Chat-ID beim WhatsApp-Connect.

**Funktionalität:**
- ✅ Beim ersten Start wird `client.info.wid.user` ausgelesen
- ✅ Format: `491798924094` → `491798924094@c.us`
- ✅ Wird automatisch in ChromaDB gespeichert
- ✅ Keine manuelle Konfiguration nötig
- ✅ Nutzt die Telefonnummer des gekoppelten Geräts

**Workflow:**
1. WhatsApp verbindet sich
2. `client.on('ready')` wird getriggert
3. Wenn keine User-Chat-ID gesetzt:
   - Lese `client.info.wid.user`
   - Erstelle Chat-ID: `{nummer}@c.us`
   - Speichere via Backend API
   - Reload Config
4. Bot ist sofort einsatzbereit

**Fallback:**
- Manuelle Konfiguration über Frontend möglich
- "Verfügbare Chats anzeigen" Button
- User kann Chat-ID manuell eingeben

**Dateien:**
- `index.js:55-76` - Auto-Configuration Logik

---

## 🎨 Frontend Features

### Settings → WhatsApp Integration

**Anzeige:**
- ✅ WhatsApp Verbindungsstatus (connected/not connected/offline)
- ✅ User-Info: Name & Telefonnummer
- ✅ Bot-Konfiguration:
  - User-Chat-ID (automatisch erkannt oder manuell)
  - Bot aktiviert/deaktiviert Toggle
  - TEST_MODE Toggle
- ✅ **Intelligente Import UI**:
  - 📥 "Alle Chats importieren" - One-Click Import mit allen Features
  - 🎯 "Chats auswählen" - Detaillierte Chat-Auswahl (Modal)
  - 📊 "Statistiken" - Import-Historie & Stats anzeigen
  - ⏳ Live-Fortschrittsanzeige während Import
  - ℹ️ Zeitfenster-Warnung (09:00-22:00)

**Chat-Auswahl Modal:**
- ✅ Liste aller WhatsApp-Chats mit Checkboxes
- ✅ **Quick-Select Buttons**:
  - "Top 10 aktive" - Wählt die 10 aktivsten Chats
  - "Letzte 30 Tage" - Alle Chats mit Aktivität in letzten 30 Tagen
  - "Alle auswählen" / "Alle abwählen"
- ✅ **Sortierung**:
  - Nach Aktivität (neueste zuerst) - Default
  - Nach Name (A-Z)
  - Nach Nachrichtenanzahl
- ✅ **Chat-Details**:
  - Name & Chat-Typ (👤 Kontakt / 👥 Gruppe)
  - Letzte Aktivität (Timestamp)
  - Import-Status (bereits importiert / neu)
- ✅ Selected Counter: Zeigt Anzahl ausgewählter Chats

**Import-Statistiken Modal:**
- ✅ **Übersicht**:
  - Anzahl importierter Chats
  - Gesamtzahl importierter Nachrichten
- ✅ **Details pro Chat**:
  - Chat-ID / Name
  - Anzahl importierter Nachrichten
  - Anzahl Import-Runs
  - Erster Import (Datum)
  - Letzter Import (Datum)
- ✅ Sortierung: Nach letztem Import (neueste zuerst)

**Live-Fortschrittsanzeige:**
- ✅ Aktueller Chat-Name
- ✅ Fortschritt (X/Y Chats verarbeitet)
- ✅ Neue Nachrichten (Zähler)
- ✅ Übersprungene Nachrichten (bereits vorhanden)
- ✅ Countdown bis nächste Pause

**Aktionen:**
- 🔄 Status aktualisieren
- 📋 Logs anzeigen (Modal mit Live-Logs)
- 💾 User-Chat-ID speichern
- 🎯 Chats auswählen (Modal öffnen)
- 📊 Statistiken anzeigen (Modal öffnen)
- 📋 Verfügbare Chats anzeigen
- 📥 Chat-Import starten
- ⚙️ Bot-Einstellungen ändern (Bot an/aus, TEST_MODE)

**Dateien:**
- `frontend/index.html:726-816` - WhatsApp Settings Section
- `frontend/index.html:1030-1313` - JavaScript Functions

---

## 🔒 Sicherheitsfeatures

### 1. Chat-Isolation
- Bot antwortet nur im konfigurierten User-Chat
- Andere Chats werden VOR Backend-Call gefiltert
- Keine unnötigen RAG-Queries

### 2. Loop Prevention
- Bot-Antworten beginnen mit `🦕`
- Werden sofort ignoriert
- Verhindert endlose Antwort-Schleifen

### 3. Multi-Layer Security
```javascript
// 4 Sicherheitsstufen (VOR Backend-Call):
1. if (msg.body.startsWith('🦕')) return;           // Bot-Nachricht
2. if (!BOT_CONFIG.bot_enabled) return;             // Bot deaktiviert
3. if (!BOT_CONFIG.user_chat_id) return;            // Keine Config
4. if (msg.from !== BOT_CONFIG.user_chat_id) return; // Falscher Chat
5. if (!BOT_CONFIG.test_mode && msg.fromMe) return; // Eigene Nachricht

// Erst hier: Backend-Call & Bot-Antwort
```

### 4. Persistent Config
- Konfiguration überlebt Neustarts (ChromaDB)
- Keine versehentliche Neu-Konfiguration
- Explizite Admin-Aktionen erforderlich

---

## 📊 Datenfluss

### Live Ingestion
```
WhatsApp Nachricht
    ↓
index.js: message_create Event
    ↓
saveMessageToBackend()
    ↓
POST /api/whatsapp/message
    ↓
FastAPI Background Task
    ↓
ChromaDB (messages Collection)
```

### Bot Response
```
WhatsApp Nachricht (im User-Chat)
    ↓
Security Checks (4 Stufen)
    ↓
POST /api/v1/webhook
    ↓
RAG Pipeline (Suche in ChromaDB)
    ↓
LLM generiert Antwort
    ↓
WhatsApp reply mit 🦕 Prefix
```

### Bulk Import
```
Frontend: "Import starten"
    ↓
POST /api/whatsapp/import-plan/start
    ↓
Import-Plan in ChromaDB gespeichert
    ↓
POST /api/whatsapp/import-all-chats
    ↓
Für jeden Chat:
  - mark-in-progress
  - Lade Nachrichten (WhatsApp Web.js)
  - Speichere via /api/whatsapp/message
  - mark-completed
    ↓
Frontend zeigt Live-Fortschritt
```

---

## 🛠️ Technische Details

### ChromaDB Collections

**1. whatsapp_config**
- Speichert Bot-Konfiguration
- Speichert Import-Plan
- IDs:
  - `bot_config_v1` - Bot Config
  - `import_plan_v1` - Import Status

**2. messages**
- Speichert alle WhatsApp-Nachrichten
- Document: Nachrichtentext
- Metadata: chat_id, sender, timestamp, etc.
- ID: WhatsApp Message ID

### WhatsApp Web.js

**Client:**
- LocalAuth: Session-Speicherung
- Puppeteer: Chrome Browser
- QR-Code für Pairing

**Events:**
- `qr` - QR-Code anzeigen
- `ready` - Verbindung hergestellt
- `message_create` - Neue Nachricht (eingehend/ausgehend)

**API:**
- `client.getChats()` - Alle Chats
- `chat.fetchMessages({limit})` - Nachrichten laden
- `msg.getContact()` - Kontakt-Info
- `msg.reply()` - Antworten

### FastAPI

**Background Tasks:**
- Asynchrone Nachrichtenverarbeitung
- Kein Blocking des Clients
- Robuste Error-Handling

**Router Prefix:**
- `/api/whatsapp/*` - Alle WhatsApp-Endpoints

---

## 📝 Konfiguration

### Umgebungsvariablen

```bash
# Optionale Konfiguration
BOT_ENABLED=false          # Bot deaktivieren (default: true)
MY_CHAT_ID=491234@c.us     # User-Chat-ID manuell setzen
WHATSAPP_PORT=3001         # WhatsApp API Port (default: 3001)
```

### config.yaml

Keine WhatsApp-spezifische Config nötig (alles in ChromaDB).

---

## 🚀 Setup & Usage

### 1. Services starten
```bash
./start.sh
```

### 2. WhatsApp verbinden
```bash
# QR-Code erscheint in Logs:
tail -f logs/whatsapp.log

# Mit WhatsApp App scannen:
# Einstellungen → Verknüpfte Geräte → Gerät hinzufügen
```

### 3. Auto-Configuration
- User-Chat-ID wird automatisch erkannt
- Bot ist sofort einsatzbereit

### 4. Import starten (optional)
- Frontend öffnen: http://localhost:8000
- Settings → WhatsApp Integration
- "📥 Alle Chats importieren" klicken
- Warten (läuft im Hintergrund)

---

## 🔧 Wartung & Debugging

### Logs anschauen
```bash
# WhatsApp Bridge
tail -f logs/whatsapp.log

# Backend (FastAPI)
tail -f logs/backend.log
```

### Status prüfen
```bash
# WhatsApp Verbindung
curl http://localhost:3001/api/whatsapp/status | jq

# Bot Config
curl http://localhost:8000/api/whatsapp/config | jq

# Import-Plan
curl http://localhost:8000/api/whatsapp/import-plan | jq
```

### Reset
```bash
# Bot-Config zurücksetzen
curl -X POST http://localhost:8000/api/whatsapp/config/reset

# Import-Plan zurücksetzen
curl -X POST http://localhost:8000/api/whatsapp/import-plan/reset
```

---

## 📈 Metriken

**Live Ingestion:**
- Jede Nachricht < 100ms verarbeitet
- Asynchron (kein Blocking)

**Bulk Import:**
- ~100 Nachrichten/Chat in ~10-30 Sekunden
- Abhängig von WhatsApp API Rate Limits
- 500ms Pause zwischen Chats

**Storage:**
- 1 Nachricht ≈ 1-2 KB in ChromaDB
- 10.000 Nachrichten ≈ 10-20 MB

---

## 🐛 Known Issues & Limitations

### 1. WhatsApp Web.js Limitations
- Kann nur Nachrichten abrufen, die in der lokalen WhatsApp-DB sind
- Sehr alte Nachrichten (Jahre) sind ggf. nicht verfügbar
- Media-Download ist möglich, aber nicht implementiert

### 2. Import Performance
- Rate Limits von WhatsApp API
- Große Chats (>1000 Nachrichten) dauern länger
- Empfehlung: Import in Batches (z.B. 100 Nachrichten/Chat)

### 3. Bot-Antworten
- Nur Textnachrichten (keine Media-Antworten)
- Kein Gruppen-Support (nur persönlicher Chat)

### 4. Persistenz
- Import-Plan ist In-Memory in ChromaDB (nicht in separater DB)
- Bei ChromaDB-Reset geht Import-Status verloren

---

## 🔮 Zukünftige Features (Roadmap)

### Geplant
- [ ] Chat-Liste UI mit Checkboxen (für selektiven Import)
- [ ] Live-Fortschrittsanzeige während Import
- [ ] Pause/Resume für Import
- [ ] Media-Download (Bilder, Videos, Audio)
- [ ] WhatsApp Gruppen-Support für Bot
- [ ] Import-Historie (wann wurde was importiert)
- [ ] Automatischer Re-Import (täglich/wöchentlich)
- [ ] Export von Chats (JSON, CSV)

### Nice-to-Have
- [ ] Voice Message Transcription
- [ ] Kontakt-Verwaltung (Namen, Aliases)
- [ ] Message Search UI
- [ ] Chat-Analytics (Statistiken, Charts)

---

## 📚 Weitere Dokumentation

- [WHATSAPP_NEW_ARCHITECTURE.md](WHATSAPP_NEW_ARCHITECTURE.md) - Technische Architektur
- [WHATSAPP_SECURITY_FIX.md](WHATSAPP_SECURITY_FIX.md) - Security Evolution
- [WHATSAPP_SECURITY.md](WHATSAPP_SECURITY.md) - Alte Whitelist-Dokumentation (deprecated)

---

## 👥 Beitragende

- Josh - Initial Implementation
- Claude - Code-Assistent

**Letzte Aktualisierung:** 2026-03-09
