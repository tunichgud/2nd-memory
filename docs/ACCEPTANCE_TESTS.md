# Memosaur -- Akzeptanztest-Spezifikation

Stand: 16.03.2026 | Erstellt von: @qs (Quality Assurance Agent)

---

## Inhaltsverzeichnis

1. [Sicherheitskritische Tests (WhatsApp Send-Guard)](#1-sicherheitskritische-tests-whatsapp-send-guard)
2. [Daten-Ingestion](#2-daten-ingestion)
3. [Chat / RAG Pipeline](#3-chat--rag-pipeline)
4. [Gesichtserkennung / Entity Resolution](#4-gesichtserkennung--entity-resolution)
5. [Speech-to-Text (STT)](#5-speech-to-text-stt)
6. [User-Verwaltung](#6-user-verwaltung)
7. [Infrastruktur](#7-infrastruktur)
8. [Sicherheitsanalyse: assertSendAllowed()](#8-sicherheitsanalyse-assertsendallowed)
9. [Chat Interface (UI)](#9-chat-interface-ui)

---

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| LOCK-SECURITY | Sicherheitskritisch -- Merge-Blocker, darf NICHT umgangen werden |
| Unit | Reine Python/JS-Logik, keine externen Abhaengigkeiten |
| Integration | Braucht DB/ChromaDB, aber kein echtes WhatsApp/Google |
| Manual | Braucht echte 3rd-Party-APIs (WhatsApp, Google, LLM) |

---

## 1. Sicherheitskritische Tests (WhatsApp Send-Guard)

### Kontext und Bedrohungsmodell

Memosaur hat genau **drei Codepfade**, ueber die eine WhatsApp-Nachricht gesendet wird:

| # | Codepfad | Datei | Zeile | Schutzmechanismus |
|---|----------|-------|-------|-------------------|
| 1 | Bot-Antwort via `msg.reply()` | `index.js` | 275 | 4-Stufen-Sicherheitslogik (Zeilen 231-254) |
| 2 | STT-Zusammenfassung via `client.sendMessage()` | `index.js` | 169, 180 | `assertSendAllowed()` |
| 3 | REST-Endpoint `POST /api/whatsapp/send` | `index.js` | 388-403 | **KEINER (SCHWACHSTELLE)** |

**Invariante:** Es darf NIEMALS eine Nachricht an eine andere Person als den gekoppelten WhatsApp-Nutzer gesendet werden.

---

### 1.1 assertSendAllowed() -- Kern-Guard-Funktion

**Testbarkeit:** Unit (Node.js)
**Existierende Tests:** `tests/whatsapp/test_send_guard.js`, `tests/whatsapp/test_voice_send_guard.js`, `tests/test_voice_send_safety.py`

#### AT-SEC-001: Fremde Chat-ID wird blockiert LOCK-SECURITY

```
GIVEN  config.user_chat_id = "491701234567@c.us"
WHEN   assertSendAllowed("491709876543@c.us", config) wird aufgerufen
THEN   wird ein Error mit Prefix "Safety:" geworfen
AND    die Error-Message enthaelt die blockierte Chat-ID "491709876543@c.us"
```

#### AT-SEC-002: Gruppenchat wird blockiert LOCK-SECURITY

```
GIVEN  config.user_chat_id = "491701234567@c.us"
WHEN   assertSendAllowed("123456789@g.us", config) wird aufgerufen
THEN   wird ein Error mit Prefix "Safety:" geworfen
```

#### AT-SEC-003: Eigener Chat wird erlaubt LOCK-SECURITY

```
GIVEN  config.user_chat_id = "491701234567@c.us"
WHEN   assertSendAllowed("491701234567@c.us", config) wird aufgerufen
THEN   wird KEIN Error geworfen
```

#### AT-SEC-004: Fehlende Konfiguration blockiert LOCK-SECURITY

```
GIVEN  config.user_chat_id = null
WHEN   assertSendAllowed("491701234567@c.us", config) wird aufgerufen
THEN   wird ein Error mit Prefix "Safety:" geworfen
```

```
GIVEN  config.user_chat_id = "" (leerer String)
WHEN   assertSendAllowed("491701234567@c.us", config) wird aufgerufen
THEN   wird ein Error mit Prefix "Safety:" geworfen
```

#### AT-SEC-005: Edge Cases blockieren LOCK-SECURITY

```
GIVEN  config.user_chat_id = "491701234567@c.us"
WHEN   assertSendAllowed(undefined, config) wird aufgerufen
THEN   wird ein Error geworfen (kein Crash)

WHEN   assertSendAllowed(null, config) wird aufgerufen
THEN   wird ein Error geworfen (kein Crash)

WHEN   assertSendAllowed("", config) wird aufgerufen
THEN   wird ein Error geworfen (kein Crash)
```

---

### 1.2 Chat-Routing (4-Stufen-Sicherheit fuer Bot-Antworten)

**Testbarkeit:** Unit (Node.js -- Logik-Extrakt)
**Existierende Tests:** `tests/whatsapp/test_chat_routing.js`

#### AT-SEC-010: Bot antwortet nur im Selbst-Chat LOCK-SECURITY

```
GIVEN  BOT_CONFIG.bot_enabled = true
AND    BOT_CONFIG.user_chat_id = "491701234567@c.us"
AND    BOT_CONFIG.test_mode = false
WHEN   eine Nachricht mit msg.from = user_chat_id AND msg.id.remote = user_chat_id AND msg.fromMe = false empfangen wird
THEN   wird die Nachricht an den Webhook weitergeleitet
AND    die Antwort wird via msg.reply() im gleichen Chat gesendet
```

#### AT-SEC-011: Eigene Nachricht an Sarah wird NICHT verarbeitet LOCK-SECURITY

```
GIVEN  BOT_CONFIG.user_chat_id = "491701234567@c.us"
WHEN   eine Nachricht mit msg.from = user_chat_id AND msg.id.remote = "491709876543@c.us" empfangen wird
THEN   wird die Nachricht NICHT an den Webhook weitergeleitet
AND    es wird KEINE Antwort gesendet
```

Hinweis: Dies ist der Kern-Regressionstest fuer den Bug, bei dem WhatsApp
bei `fromMe=true` immer die eigene Telefonnummer als `msg.from` zurueckgibt,
unabhaengig vom Ziel-Chat.

#### AT-SEC-012: Bot-Nachrichten-Loop-Prevention LOCK-SECURITY

```
GIVEN  eine Nachricht beginnt mit dem Emoji-Prefix (Dino)
WHEN   message_create Event ausgeloest wird
THEN   wird die Nachricht sofort ignoriert (return)
AND    es wird KEIN Webhook-Aufruf ausgeloest
AND    es wird KEINE Antwort gesendet
```

```
GIVEN  eine Nachricht beginnt mit "[STT]" oder "[STT Fehler]"
WHEN   message_create Event ausgeloest wird
THEN   wird die Nachricht sofort ignoriert (Loop Prevention)
```

#### AT-SEC-013: Bot deaktiviert -- keine Verarbeitung

```
GIVEN  BOT_CONFIG.bot_enabled = false
WHEN   eine beliebige Nachricht empfangen wird
THEN   wird die Nachricht NICHT an den Webhook weitergeleitet
```

#### AT-SEC-014: Keine User-Chat-ID -- keine Verarbeitung

```
GIVEN  BOT_CONFIG.user_chat_id = null
WHEN   eine beliebige Nachricht empfangen wird
THEN   wird die Nachricht NICHT an den Webhook weitergeleitet
```

---

### 1.3 STT-Sendeweg (Voice Messages)

**Testbarkeit:** Unit (Node.js) + Integration (Python)
**Existierende Tests:** `tests/test_voice_send_safety.py`, `tests/whatsapp/test_voice_send_guard.js`

#### AT-SEC-020: handleVoiceMessage ruft assertSendAllowed auf LOCK-SECURITY

```
GIVEN  index.js Quellcode
WHEN   der Funktionskoerper von handleVoiceMessage analysiert wird
THEN   enthaelt er mindestens einen Aufruf von assertSendAllowed()
AND    dieser Aufruf steht VOR jedem client.sendMessage()-Aufruf
```

**Testmethode:** Strukturelle Quellcode-Analyse (fs.readFileSync + RegEx).
Kein Mock, kein Stub -- der Test liest die echte Datei.

#### AT-SEC-021: STT-Zusammenfassung geht nur an eigenen Chat LOCK-SECURITY

```
GIVEN  BOT_CONFIG.user_chat_id = "491701234567@c.us"
AND    eine Sprachnachricht von "491709876543@c.us" (Sarah) empfangen wird
WHEN   handleVoiceMessage die Zusammenfassung senden will
THEN   wird assertSendAllowed(config.user_chat_id, config) aufgerufen
AND    die Zusammenfassung wird an "491701234567@c.us" (den eigenen Chat) gesendet
AND    die Zusammenfassung wird NICHT an "491709876543@c.us" (Sarahs Chat) gesendet
```

#### AT-SEC-022: STT-Endpoint sendet nicht selbst LOCK-SECURITY

```
GIVEN  eine POST-Anfrage an /api/v1/stt/transcribe
WHEN   die Transkription erfolgreich ist
THEN   enthaelt die Response ein "formatted_message"-Feld
AND    die Response enthaelt KEIN "sent_to"-Feld
AND    der Endpoint ruft KEIN client.sendMessage() auf
```

Das Senden ist ausschliesslich Aufgabe der WhatsApp-Bridge (index.js).

---

### 1.4 REST-Endpoint /api/whatsapp/send -- SCHWACHSTELLE

**Testbarkeit:** Unit (Node.js)
**Status: KEIN assertSendAllowed-Aufruf vorhanden -- offene Schwachstelle**

#### AT-SEC-030: /api/whatsapp/send MUSS assertSendAllowed aufrufen LOCK-SECURITY

```
GIVEN  index.js Quellcode
WHEN   der Handler fuer POST /api/whatsapp/send analysiert wird
THEN   enthaelt er einen Aufruf von assertSendAllowed(chatId, BOT_CONFIG)
AND    dieser Aufruf steht VOR dem chat.sendMessage()-Aufruf
AND    bei Safety-Error wird HTTP 403 zurueckgegeben (nicht 500)
```

**Status:** FAIL -- Dieser Test ist aktuell ROT. Der Endpoint auf Zeile 388-403
von `index.js` ruft `chat.sendMessage(message)` auf OHNE vorher
`assertSendAllowed()` zu pruefen. Jeder HTTP-Client kann an beliebige
Chat-IDs Nachrichten senden.

#### AT-SEC-031: /api/whatsapp/send blockiert fremde Chat-IDs LOCK-SECURITY

```
GIVEN  BOT_CONFIG.user_chat_id = "491701234567@c.us"
WHEN   POST /api/whatsapp/send mit chatId = "491709876543@c.us" aufgerufen wird
THEN   wird HTTP 403 zurueckgegeben
AND    der Response-Body enthaelt {"error": "Safety: ..."}
AND    es wird KEINE Nachricht ueber WhatsApp gesendet
```

#### AT-SEC-032: /api/whatsapp/send blockiert Gruppenchats LOCK-SECURITY

```
GIVEN  BOT_CONFIG.user_chat_id = "491701234567@c.us"
WHEN   POST /api/whatsapp/send mit chatId = "123456789@g.us" aufgerufen wird
THEN   wird HTTP 403 zurueckgegeben
AND    es wird KEINE Nachricht gesendet
```

---

### 1.5 Strukturelle Sicherheitstests (Anti-Tamper)

Diese Tests pruefen den Quellcode direkt und koennen nicht durch Aendern
der Laufzeit-Logik umgangen werden.

#### AT-SEC-040: Jeder sendMessage-Aufruf ist durch assertSendAllowed geschuetzt LOCK-SECURITY

```
GIVEN  index.js Quellcode
WHEN   alle Vorkommen von "sendMessage" oder ".reply(" identifiziert werden
THEN   steht vor jedem Vorkommen (in der gleichen Funktion / im gleichen Handler)
       ein Aufruf von assertSendAllowed()
       ODER das sendMessage ist ein msg.reply() innerhalb des 4-Stufen-Guards
       (dessen Bedingung msg.from === user_chat_id && msg.id.remote === user_chat_id umfasst)
```

**Testmethode:** AST-Analyse oder String-basierte Quellcode-Analyse.
Der Test liest `index.js` via `fs.readFileSync` und prueft alle Sendepfade.

#### AT-SEC-041: assertSendAllowed ist als module.exports exponiert LOCK-SECURITY

```
GIVEN  index.js Quellcode
WHEN   module.exports analysiert wird
THEN   enthaelt es die Funktion assertSendAllowed
```

Ohne Export kann die Funktion nicht in Tests importiert und verifiziert werden.

#### AT-SEC-042: assertSendAllowed fuehrt strikte Gleichheitspruefung durch LOCK-SECURITY

```
GIVEN  index.js Quellcode
WHEN   der Funktionskoerper von assertSendAllowed analysiert wird
THEN   verwendet er === (strikte Gleichheit) oder !== fuer den Vergleich
AND    er verwendet NICHT == oder != (lose Gleichheit)
AND    er verwendet KEINE RegExp oder .includes() fuer den Chat-ID-Vergleich
```

Lose Vergleiche koennten durch Type Coercion umgangen werden.

---

## 2. Daten-Ingestion

### 2.1 WhatsApp Chat-Import (TXT-Export)

**Testbarkeit:** Integration (ChromaDB)

#### AT-ING-001: WhatsApp TXT-Datei erfolgreich importieren

```
GIVEN  eine WhatsApp-TXT-Exportdatei im Android-Format (z.B. "[01.01.2025, 12:00:00] Sender: Text")
WHEN   POST /api/v1/ingest/messages mit source_type=whatsapp aufgerufen wird
THEN   wird HTTP 200 zurueckgegeben
AND    die Response enthaelt die Anzahl importierter Nachrichten
AND    die Nachrichten sind in der ChromaDB-Collection "messages" auffindbar
```

#### AT-ING-002: iOS-Format wird ebenfalls erkannt

```
GIVEN  eine WhatsApp-TXT-Exportdatei im iOS-Format (z.B. "[01.01.2025, 12:00:00 PM] Sender: Text")
WHEN   POST /api/v1/ingest/messages mit source_type=whatsapp aufgerufen wird
THEN   werden die Nachrichten korrekt geparst und importiert
```

#### AT-ING-003: System-Messages werden gefiltert

```
GIVEN  eine WhatsApp-TXT-Datei die "<Medien weggelassen>" enthaelt
WHEN   die Datei importiert wird
THEN   werden System-Messages NICHT in ChromaDB indexiert
AND    nur echte Chat-Nachrichten werden gespeichert
```

#### AT-ING-004: Mehrzeilige Nachrichten werden zusammengefuegt

```
GIVEN  eine WhatsApp-Nachricht die ueber mehrere Zeilen geht (ohne neuen Timestamp-Header)
WHEN   die Datei importiert wird
THEN   werden alle Zeilen zu einer einzigen Nachricht zusammengefuegt
```

#### AT-ING-005: User-Isolation bei Import

```
GIVEN  User A importiert eine WhatsApp-TXT-Datei
WHEN   User B nach diesen Nachrichten sucht
THEN   findet User B KEINE Ergebnisse (user_id-Filter in ChromaDB)
```

---

### 2.2 WhatsApp Live-Ingestion (Bridge)

**Testbarkeit:** Integration (Backend) / Manual (WhatsApp-Verbindung)

#### AT-ING-010: Live-Nachricht wird in ChromaDB gespeichert

```
GIVEN  die WhatsApp-Bridge ist verbunden
WHEN   eine Nachricht im WhatsApp-Chat eingeht
THEN   wird die Nachricht via POST /api/whatsapp/message an das Backend gesendet
AND    die Nachricht ist anschliessend in der ChromaDB-Collection "messages" auffindbar
AND    die Metadaten enthalten chat_id, chat_name, sender, timestamp
```

#### AT-ING-011: Bulk-Import dedupliziert korrekt

```
GIVEN  Chat X wurde bereits importiert (100 Nachrichten, letzter Timestamp = T1)
WHEN   POST /api/whatsapp/import-all-chats erneut aufgerufen wird
AND    Chat X hat 10 neue Nachrichten (Timestamp > T1)
THEN   werden nur die 10 neuen Nachrichten importiert
AND    die 100 alten Nachrichten werden NICHT doppelt importiert
```

#### AT-ING-012: Rate Limiting wird eingehalten

```
GIVEN  ein Bulk-Import laeuft
WHEN   10 Chats importiert wurden
THEN   wird eine Pause von 60 Sekunden eingelegt
AND    zwischen jedem einzelnen Chat wird 3 Sekunden gewartet
```

#### AT-ING-013: Bulk-Import nur im Zeitfenster

```
GIVEN  die aktuelle Uhrzeit ist 23:00 (ausserhalb 09:00-22:00)
WHEN   POST /api/whatsapp/import-all-chats aufgerufen wird
THEN   wird HTTP 400 zurueckgegeben mit Fehlerhinweis auf das Zeitfenster
```

---

### 2.3 Signal Messenger Import

**Testbarkeit:** Integration (ChromaDB)

#### AT-ING-020: Signal JSON-Export importieren

```
GIVEN  eine Signal Desktop Backup-Datei (messages.json)
WHEN   POST /api/v1/ingest/messages mit source_type=signal aufgerufen wird
THEN   werden die Nachrichten in ChromaDB indexiert
AND    die Metadaten enthalten source=signal
```

---

### 2.4 Google Fotos Import

**Testbarkeit:** Integration (ChromaDB + Dateisystem) / Manual (Vision-LLM)

#### AT-ING-030: Foto mit Sidecar-JSON importieren

```
GIVEN  ein Foto (IMG_001.jpg) mit zugehoeriger Sidecar-JSON (IMG_001.jpg.json)
AND    die JSON enthaelt GPS-Koordinaten und Datum
WHEN   POST /api/v1/ingest/photos/submit aufgerufen wird
THEN   wird das Foto in der Collection "photos" gespeichert
AND    die Metadaten enthalten lat, lon, date_iso, place_name
```

#### AT-ING-031: Vision-LLM Bildbeschreibung

```
GIVEN  ein Foto (IMG_001.jpg)
WHEN   POST /api/v1/ingest/photos/describe aufgerufen wird
THEN   wird eine KI-generierte Bildbeschreibung zurueckgegeben
AND    die Beschreibung ist als "description"-Feld in der Response
```

#### AT-ING-032: Foto nicht gefunden gibt 404

```
GIVEN  ein Dateiname der nicht existiert ("nicht_da.jpg")
WHEN   POST /api/v1/ingest/photos/describe aufgerufen wird
THEN   wird HTTP 404 zurueckgegeben
```

---

### 2.5 Google Maps Bewertungen

**Testbarkeit:** Integration (ChromaDB + Dateisystem)

#### AT-ING-040: Reviews importieren

```
GIVEN  eine Bewertungen.json aus Google Takeout
WHEN   POST /api/v1/ingest/reviews aufgerufen wird
THEN   werden die Bewertungen in der Collection "reviews" gespeichert
AND    die Response enthaelt die Anzahl importierter Bewertungen
```

#### AT-ING-041: User muss existieren

```
GIVEN  ein nicht existierender user_id = "fake_user_123"
WHEN   POST /api/v1/ingest/reviews aufgerufen wird
THEN   wird HTTP 404 zurueckgegeben mit "User nicht gefunden"
```

---

### 2.6 Google Maps Gespeicherte Orte

**Testbarkeit:** Integration (ChromaDB + Dateisystem)

#### AT-ING-050: Saved Places importieren

```
GIVEN  eine "Gespeicherte Orte.json" aus Google Takeout
WHEN   POST /api/v1/ingest/saved aufgerufen wird
THEN   werden die Orte in der Collection "saved_places" gespeichert
```

---

### 2.7 Ingestion-Status

**Testbarkeit:** Integration (ChromaDB)

#### AT-ING-060: Status gibt Dokumentzaehler pro Collection

```
GIVEN  User X hat 50 Nachrichten, 10 Fotos, 5 Reviews, 3 Saved Places importiert
WHEN   GET /api/v1/ingest/status?user_id=X aufgerufen wird
THEN   enthaelt die Response: {"messages": 50, "photos": 10, "reviews": 5, "saved_places": 3}
```

#### AT-ING-061: Leerer User gibt Nullen zurueck

```
GIVEN  User Y hat nichts importiert
WHEN   GET /api/v1/ingest/status?user_id=Y aufgerufen wird
THEN   enthaelt die Response: {"messages": 0, "photos": 0, "reviews": 0, "saved_places": 0}
```

---

## 3. Chat / RAG Pipeline

### 3.1 Streaming RAG (v3)

**Testbarkeit:** Integration (ChromaDB + LLM)

#### AT-RAG-001: SSE-Stream liefert erwartete Event-Typen

```
GIVEN  der User hat Nachrichten in ChromaDB
WHEN   POST /api/v1/query_stream mit query="Wann war ich in Muenchen?" aufgerufen wird
THEN   werden SSE-Events gestreamt
AND    mindestens folgende Event-Typen kommen vor: "sources", "text"
AND    jedes Event ist ein gueltiges JSON-Objekt mit "type" und "content" Feldern
```

#### AT-RAG-002: Leere Datenbank gibt sinnvolle Antwort

```
GIVEN  der User hat keine Daten in ChromaDB
WHEN   POST /api/v1/query_stream mit einer beliebigen Frage aufgerufen wird
THEN   enthaelt die LLM-Antwort einen Hinweis dass keine Daten gefunden wurden
AND    es werden KEINE halluzinierten Fakten zurueckgegeben
```

#### AT-RAG-003: Chat-Historie wird mitgesendet

```
GIVEN  der User hat bereits 3 Fragen in der Session gestellt
WHEN   POST /api/v1/query_stream mit chat_history (3 Eintraege) aufgerufen wird
THEN   werden die letzten 10 Nachrichten der Historie an das LLM uebergeben
AND    das LLM kann sich auf vorherige Fragen beziehen
```

---

### 3.2 Query-Parsing (LLM-basiert)

**Testbarkeit:** Integration (LLM noetig)

#### AT-RAG-010: Personen werden aus Frage extrahiert

```
GIVEN  keine Filter vom Frontend uebergeben
WHEN   die Query "Was hat Sarah letzte Woche geschrieben?" geparst wird
THEN   wird persons=["Sarah"] extrahiert
AND    ein passender Datumsfilter fuer "letzte Woche" wird gesetzt
```

#### AT-RAG-011: Orte werden aus Frage extrahiert

```
GIVEN  keine Filter vom Frontend uebergeben
WHEN   die Query "Welche Restaurants war ich in Muenchen?" geparst wird
THEN   wird locations=["Muenchen"] extrahiert
```

---

### 3.3 Hybrid-Retrieval

**Testbarkeit:** Integration (ChromaDB)

#### AT-RAG-020: Semantische Suche findet relevante Dokumente

```
GIVEN  die Collection "messages" enthaelt "Wir treffen uns morgen im Biergarten"
WHEN   retrieve_v2(query="Biergarten Treffen") aufgerufen wird
THEN   wird das Dokument mit score > 0.5 zurueckgegeben
```

#### AT-RAG-021: Multi-Collection-Suche

```
GIVEN  relevante Daten in "messages", "photos" und "reviews"
WHEN   retrieve_v2 ohne collections-Filter aufgerufen wird
THEN   werden Ergebnisse aus allen durchsuchbaren Collections zurueckgegeben
AND    die Ergebnisse sind nach (is_relevant, score) sortiert
```

#### AT-RAG-022: User-Isolation bei Retrieval

```
GIVEN  User A hat Nachrichten in ChromaDB
AND    User B hat andere Nachrichten in ChromaDB
WHEN   retrieve_v2(user_id="A") aufgerufen wird
THEN   werden NUR Dokumente von User A zurueckgegeben
AND    es werden KEINE Dokumente von User B zurueckgegeben
```

#### AT-RAG-023: Personen-Post-Filter

```
GIVEN  ChromaDB enthaelt Nachrichten von Sarah, Marius und Nora
WHEN   retrieve_v2(person_names=["Sarah"]) aufgerufen wird
THEN   enthalten alle zurueckgegebenen Dokumente "Sarah" in den Metadaten oder im Text
```

#### AT-RAG-024: Datums-Filter

```
GIVEN  ChromaDB enthaelt Nachrichten aus 2024 und 2025
WHEN   retrieve_v2(date_from="2025-01-01", date_to="2025-12-31") aufgerufen wird
THEN   werden NUR Nachrichten mit date_ts im Jahr 2025 zurueckgegeben
```

---

### 3.4 Context Window Management

**Testbarkeit:** Unit (Python)

#### AT-RAG-030: Context Compression reduziert Token-Anzahl

```
GIVEN  50 Source-Dokumente mit insgesamt ~6000 Tokens
WHEN   compress_sources(sources, budget=ContextBudget(max_tokens=2000)) aufgerufen wird
THEN   ist der resultierende Text kleiner als 2000 Tokens
AND    die wichtigsten Quellen (hoechster Score) sind vollstaendig enthalten
```

#### AT-RAG-031: Quellen-Formatierung enthaelt Metadaten

```
GIVEN  eine Quelle aus der Collection "photos" mit date_iso, cluster, place_name
WHEN   _format_sources_for_llm aufgerufen wird
THEN   enthaelt der formatierte Text den Quellen-Typ, das Datum und den Ort
AND    GPS-Koordinaten werden angezeigt wenn lat != 0.0
```

---

### 3.5 WhatsApp Bot (Selbst-Chat)

**Testbarkeit:** Integration (Backend) / Manual (WhatsApp)

#### AT-RAG-040: Webhook verarbeitet eingehende Nachrichten

```
GIVEN  der Default-User existiert in der DB
WHEN   POST /api/v1/webhook mit sender="Ich", text="Wann war ich in Rom?", is_incoming=true
THEN   wird status="success" zurueckgegeben
AND    die Response enthaelt ein "answer"-Feld mit der LLM-Antwort
AND    die Nachricht wurde in ChromaDB indexiert
```

#### AT-RAG-041: Bot-Nachrichten werden nicht beantwortet

```
GIVEN  eine Nachricht die mit dem Dino-Emoji beginnt (Bot-Prefix)
WHEN   POST /api/v1/webhook mit text="[Dino] Das ist eine Antwort", is_incoming=true
THEN   wird status="success" zurueckgegeben
AND    answer = null (keine Antwort generiert)
AND    die Nachricht wird trotzdem in ChromaDB indexiert (als KI-Nachricht)
```

#### AT-RAG-042: Ausgehende Nachrichten werden nicht beantwortet

```
GIVEN  eine ausgehende Nachricht
WHEN   POST /api/v1/webhook mit is_incoming=false
THEN   wird answer = null zurueckgegeben
AND    die Nachricht wird trotzdem in ChromaDB indexiert
```

---

## 4. Gesichtserkennung / Entity Resolution

### 4.1 Entity-Verwaltung

**Testbarkeit:** Integration (DB + ChromaDB)

#### AT-ENT-001: Entity erstellen und abrufen

```
GIVEN  ein gueltiger User
WHEN   eine neue Entity (Person) ueber den API-Endpoint erstellt wird
THEN   ist die Entity anschliessend via GET abrufbar
AND    die Entity hat eine eindeutige ID
```

#### AT-ENT-002: Cluster-zu-Person-Verknuepfung

```
GIVEN  ein DBSCAN-Cluster mit repaesentativen Bildern
WHEN   der Cluster einer Entity (z.B. "Sarah") zugeordnet wird
THEN   wird die Verknuepfung gespeichert
AND    alle Fotos im Cluster werden mit den Metadaten der Person aktualisiert
```

#### AT-ENT-003: Entity-Umbenennung aktualisiert Metadaten

```
GIVEN  eine Entity "cluster_5" mit 10 verknuepften Fotos
WHEN   die Entity in "Sarah Ohnesorge" umbenannt wird
THEN   werden die Metadaten aller 10 Fotos in ChromaDB aktualisiert
AND    die persons-Felder enthalten den neuen Namen
```

---

### 4.2 Label-Validierung

**Testbarkeit:** Integration (DB)

#### AT-ENT-010: Validierungs-Session erstellen

```
GIVEN  eine Entity mit zugeordneten Fotos
WHEN   eine Validierungs-Session gestartet wird
THEN   werden Foto-Vorschlaege mit Qualitaetsmetriken zurueckgegeben
AND    der User kann validate, reject, split oder merge waehlen
```

---

## 5. Speech-to-Text (STT)

### 5.1 Transkription

**Testbarkeit:** Integration (Whisper-Modell noetig)

#### AT-STT-001: Audio-Datei wird transkribiert

```
GIVEN  eine OGG-Audiodatei mit gesprochener Sprache
WHEN   POST /api/v1/stt/transcribe aufgerufen wird
THEN   wird status="success" zurueckgegeben
AND    die Response enthaelt transcript, language, formatted_message
```

#### AT-STT-002: Transkription wird in ChromaDB gespeichert

```
GIVEN  eine erfolgreiche Transkription
WHEN   der STT-Endpoint die Verarbeitung abschliesst
THEN   ist die Zusammenfassung in der ChromaDB-Collection "messages" auffindbar
AND    die Metadaten enthalten den originalen Sender und Chat-Namen
```

#### AT-STT-003: Fehler bei Transkription gibt status=error

```
GIVEN  eine korrupte oder leere Audio-Datei
WHEN   POST /api/v1/stt/transcribe aufgerufen wird
THEN   wird HTTP 200 mit status="error" zurueckgegeben (kein 500)
AND    formatted_message enthaelt einen Fehlerhinweis
```

---

## 6. User-Verwaltung

### 6.1 CRUD-Endpoints

**Testbarkeit:** Integration (SQLite)

#### AT-USR-001: User erstellen

```
GIVEN  ein display_name = "TestUser"
WHEN   POST /api/v1/users mit {"display_name": "TestUser"} aufgerufen wird
THEN   wird HTTP 201 zurueckgegeben
AND    die Response enthaelt id, display_name, created_at
AND    der User ist anschliessend via GET /api/v1/users/{id} abrufbar
```

#### AT-USR-002: User auflisten

```
GIVEN  es existieren 3 User in der DB
WHEN   GET /api/v1/users aufgerufen wird
THEN   wird eine Liste mit 3 Usern zurueckgegeben
AND    die Liste ist nach created_at sortiert
```

#### AT-USR-003: User-Profil aktualisieren

```
GIVEN  ein existierender User mit id = X
WHEN   PATCH /api/v1/users/X mit {"display_name": "Neuer Name"} aufgerufen wird
THEN   wird der aktualisierte User zurueckgegeben
AND    display_name = "Neuer Name"
```

#### AT-USR-004: Leerer Display-Name wird abgelehnt

```
GIVEN  ein existierender User
WHEN   PATCH /api/v1/users/X mit {"display_name": ""} aufgerufen wird
THEN   wird HTTP 400 zurueckgegeben
```

#### AT-USR-005: Display-Name maximal 100 Zeichen

```
GIVEN  ein existierender User
WHEN   PATCH /api/v1/users/X mit display_name = "A" * 101 aufgerufen wird
THEN   wird HTTP 400 zurueckgegeben
```

#### AT-USR-006: Nicht existierender User gibt 404

```
GIVEN  kein User mit id = "nonexistent"
WHEN   GET /api/v1/users/nonexistent aufgerufen wird
THEN   wird HTTP 404 zurueckgegeben
```

---

## 7. Infrastruktur

### 7.1 Health-Check

**Testbarkeit:** Integration

#### AT-INF-001: Health-Check Endpoint

```
GIVEN  das Backend laeuft
WHEN   GET /health aufgerufen wird
THEN   wird HTTP 200 zurueckgegeben
```

### 7.2 CORS

**Testbarkeit:** Integration

#### AT-INF-010: CORS erlaubt Frontend-Origin

```
GIVEN  eine Anfrage mit Origin: http://localhost:8001
WHEN   ein API-Endpoint aufgerufen wird
THEN   enthaelt die Response den Header Access-Control-Allow-Origin: http://localhost:8001
```

### 7.3 Konfiguration

**Testbarkeit:** Unit (Python)

#### AT-INF-020: config.yaml wird geladen

```
GIVEN  eine gueltige config.yaml mit llm.provider und paths.photos_dir
WHEN   get_cfg() aufgerufen wird
THEN   werden die Werte korrekt geladen
AND    fehlende Keys fuehren zu einem klaren Fehler
```

---

## 8. Sicherheitsanalyse: assertSendAllowed()

### Aktuelle Implementierung (index.js, Zeile 38-45)

```javascript
function assertSendAllowed(chatId, config) {
    if (!config.user_chat_id) {
        throw new Error('Safety: user_chat_id nicht konfiguriert');
    }
    if (chatId !== config.user_chat_id) {
        throw new Error(`Safety: Send an ${chatId} blockiert -- nur ${config.user_chat_id} erlaubt`);
    }
}
```

### Staerken

1. **Synchrone Funktion** -- kann nicht durch async Race Conditions umgangen werden
2. **Throw statt Return** -- Aufrufer muss aktiv catchen, Default ist Abbruch
3. **Strikter Vergleich (===)** -- kein Type Coercion moeglich
4. **Fail-Closed bei fehlender Config** -- wenn user_chat_id nicht gesetzt, wird alles blockiert
5. **Export via module.exports** -- Tests importieren die echte Funktion, kein Drift
6. **Safety-Prefix im Error** -- ermoeglicht 403-Erkennung im Endpoint-Layer

### Identifizierte Schwachstellen

| # | Schwachstelle | Schweregrad | Status |
|---|---------------|-------------|--------|
| S1 | `/api/whatsapp/send` ruft assertSendAllowed NICHT auf | KRITISCH | OFFEN |
| S2 | `msg.reply()` (Zeile 275) hat kein explizites assertSendAllowed -- verlaesst sich auf 4-Stufen-Guard | NIEDRIG | Akzeptabel (Guard prueft msg.from + msg.id.remote) |
| S3 | BOT_CONFIG ist ein mutabler globaler State -- theoretisch via `/api/whatsapp/config/my-chat` manipulierbar | MITTEL | Akzeptabel (nur localhost) |
| S4 | `assertSendAllowed` prueft nicht das Format der Chat-ID (z.B. `@c.us` Suffix) | NIEDRIG | Akzeptabel (WhatsApp-Client wuerde ungueltige IDs ohnehin ablehnen) |
| S5 | Kein Rate-Limiting auf dem `/api/whatsapp/send` Endpoint | NIEDRIG | Akzeptabel fuer lokales System |

### Empfehlung: Fix fuer S1

Der `POST /api/whatsapp/send` Handler muss um folgenden Guard erweitert werden:

```
// VOR chat.sendMessage(message):
assertSendAllowed(chatId, BOT_CONFIG);
```

Und der catch-Block muss Safety-Errors als HTTP 403 zurueckgeben:

```
if (err.message.startsWith('Safety:')) {
    return res.status(403).json({ error: err.message });
}
```

### Wie sind die Tests gegen Umgehung geschuetzt?

1. **Import der echten Funktion:** Tests importieren `assertSendAllowed` direkt via
   `require('../../index.js')` -- keine Kopie, kein Drift moeglich.

2. **Strukturelle Quellcode-Analyse:** `test_voice_send_guard.js` liest den Quellcode
   von `index.js` via `fs.readFileSync` und prueft, dass `assertSendAllowed` im
   Funktionskoerper von `handleVoiceMessage` vorkommt. Dieser Test kann nicht durch
   Aendern der Laufzeitlogik umgangen werden -- der Quellcode selbst wird geprueft.

3. **Cross-Language-Test:** `test_voice_send_safety.py` fuehrt die Node.js-Funktion
   in einem Subprocess aus. Ein Angreifer muesste sowohl Python- als auch JS-Tests
   aendern, um den Guard zu umgehen.

4. **Fehlender Schutz fuer /api/whatsapp/send:** Hier existiert aktuell KEIN Test
   und KEIN Guard. Dies ist der einzige Weg, ueber den ein Angreifer (oder ein Bug)
   Nachrichten an beliebige Chat-IDs senden koennte. **Muss gefixt werden.**

---

## 9. Chat Interface (UI)

### 9.1 Thinking-Mode-Toggle -- localStorage-Persistenz

**Testbarkeit:** Unit (Node.js -- kein Browser noetig)
**Existierende Tests:** `tests/frontend/test_thinking_mode_persistence.js`

**Implementierungsdetail:** Der tatsaechliche localStorage-Key in der Implementierung
lautet `thinkingModeEnabled` (nicht `memosaur_thinking_mode` wie in der urspruenglichen
Spezifikation). Die Tests pruefen den real implementierten Key.

Relevante Quellcode-Stellen:
- Speichern: `frontend/index.html` Zeile 308 (onchange-Handler des Toggle-Checkboxes)
- Wiederherstellen: `frontend/index.html` Zeilen 957-960 (initApp-Funktion)
- Verwendung: `frontend/chat.js` Zeile 73 (`use_thinking_mode` im API-Request)

---

#### AT-UI-001: Toggle ON schreibt 'true' in localStorage

```
GIVEN  Thinking Mode ist aus (toggle.checked = false)
WHEN   der Toggle-Checkbox auf checked = true gesetzt wird
THEN   wird localStorage.setItem('thinkingModeEnabled', 'true') aufgerufen
AND    window._thinkingModeEnabled === true
```

#### AT-UI-002: Toggle OFF schreibt 'false' in localStorage

```
GIVEN  Thinking Mode ist an (toggle.checked = true)
WHEN   der Toggle-Checkbox auf checked = false gesetzt wird
THEN   wird localStorage.setItem('thinkingModeEnabled', 'false') aufgerufen
AND    window._thinkingModeEnabled === false
```

#### AT-UI-003: Init mit localStorage='true' -- Thinking Mode aktiv

```
GIVEN  localStorage['thinkingModeEnabled'] === 'true'
WHEN   initApp() ausgefuehrt wird (Seite wird geladen)
THEN   ist window._thinkingModeEnabled === true
AND    toggle.checked === true (Checkbox ist visuell aktiviert)
```

#### AT-UI-004: Init mit localStorage='false' -- Thinking Mode inaktiv

```
GIVEN  localStorage['thinkingModeEnabled'] === 'false'
WHEN   initApp() ausgefuehrt wird (Seite wird geladen)
THEN   ist window._thinkingModeEnabled === false
AND    toggle.checked === false (Checkbox ist visuell deaktiviert)
```

#### AT-UI-005: Init ohne localStorage-Eintrag -- Default ist false (inaktiv)

```
GIVEN  localStorage enthaelt KEINEN Eintrag fuer 'thinkingModeEnabled'
       (localStorage.getItem('thinkingModeEnabled') gibt null zurueck)
WHEN   initApp() ausgefuehrt wird (Seite wird geladen)
THEN   ist window._thinkingModeEnabled === false
AND    toggle.checked === false (Thinking Mode ist standardmaessig aus)
```

---

## Zusammenfassung

| Kategorie | Tests gesamt | LOCK-SECURITY | Unit | Integration | Manual |
|-----------|-------------|---------------|------|-------------|--------|
| WhatsApp Send-Guard | 19 | 15 | 15 | 2 | 2 |
| Daten-Ingestion | 14 | 0 | 1 | 11 | 2 |
| Chat / RAG Pipeline | 14 | 0 | 2 | 10 | 2 |
| Gesichtserkennung | 3 | 0 | 0 | 3 | 0 |
| Speech-to-Text | 3 | 0 | 0 | 2 | 1 |
| User-Verwaltung | 6 | 0 | 0 | 6 | 0 |
| Infrastruktur | 3 | 0 | 1 | 2 | 0 |
| Chat Interface (UI) | 5 | 0 | 5 | 0 | 0 |
| **Gesamt** | **67** | **15** | **24** | **36** | **7** |

### Offene Massnahmen

| Prioritaet | Massnahme | Zustaendig |
|------------|-----------|------------|
| KRITISCH | Fix S1: assertSendAllowed in `/api/whatsapp/send` einbauen | @whatsapp-dev |
| KRITISCH | Tests AT-SEC-030 bis AT-SEC-032 implementieren | @tester |
| HOCH | Test AT-SEC-040 implementieren (alle Sendepfade geprueft) | @tester |
| MITTEL | Bestehende Tests mit `pytest -m safety` markieren (Merge-Blocker) | @tester |
