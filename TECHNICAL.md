# Technische Dokumentation – memosaur v2

## Inhaltsverzeichnis

1. [Architekturübersicht](#architekturübersicht)
2. [Verzeichnisstruktur](#verzeichnisstruktur)
3. [Token-Flow (Privacy-Kernkonzept)](#token-flow)
4. [Datenmodell](#datenmodell)
5. [Backend-Module](#backend-module)
6. [RAG-Pipelines](#rag-pipelines)
7. [API-Endpunkte](#api-endpunkte)
8. [Frontend-Module](#frontend-module)
9. [Konfiguration](#konfiguration)
10. [Abhängigkeiten](#abhängigkeiten)

---

## Architekturübersicht

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser (Client)                           │
│                                                                    │
│  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ Transformers │  │   IndexedDB     │  │  Web Crypto API     │  │
│  │ .js (WASM)   │  │  Token↔Name     │  │  AES-GCM Encrypt    │  │
│  │ NER lokal    │  │  Wörterbuch     │  │  für Sync-Blob      │  │
│  └──────┬───────┘  └──────┬──────────┘  └──────────┬──────────┘  │
│ maskiert│          lookup │                  encrypt│             │
└─────────┼─────────────────┼──────────────────────────────────────┘
          │ POST (nur Tokens)│                         │ POST /sync
          ▼                  ▼ (Re-Mapping im Browser) ▼
┌──────────────────────────────────────────────────────────────────┐
│              FastAPI Backend – /api/v0/ + /api/v1/               │
│                                                                    │
│  /v1/query  /v1/ingest  /v1/sync  /v1/consent  /v1/dictionary   │
│                                                                    │
│  ┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐  │
│  │  ChromaDB    │   │  SQLite          │   │  Ollama          │  │
│  │  (nur Tokens)│   │  users           │   │  qwen3:8b Chat   │  │
│  │  user_id-    │   │  consents        │   │  gemma3:12b      │  │
│  │  scoped      │   │  sync_blobs      │   │  Vision          │  │
│  └──────────────┘   └──────────────────┘   └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

Zwei API-Generationen laufen parallel:
- **v0** (`/api/*`): Original-API mit Klarnamen, bleibt für Rückwärtskompatibilität erhalten
- **v1** (`/api/v1/*`): Token-aware, user-scoped, DSGVO-konform

---

## Verzeichnisstruktur

```
memosaur/
├── backend/
│   ├── main.py                        # FastAPI-App, Startup (SQLite init), alle Router
│   ├── api/
│   │   ├── ingest.py                  # v0: POST /api/ingest/*
│   │   ├── query.py                   # v0: POST /api/query
│   │   ├── map.py                     # v0: GET /api/locations
│   │   ├── media.py                   # v0+v1 shared: Bild-Thumbnails
│   │   └── v1/
│   │       ├── users.py               # GET/POST /api/v1/users
│   │       ├── consent.py             # GET/POST /api/v1/consent/{user_id}
│   │       ├── sync.py                # GET/POST /api/v1/sync/{user_id}
│   │       ├── dictionary.py          # GET/DELETE /api/v1/dictionary
│   │       ├── ingest.py              # POST /api/v1/ingest/* (Consent-Gate)
│   │       ├── query.py               # POST /api/v1/query (Token-aware)
│   │       ├── map.py                 # GET /api/v1/locations (user-scoped)
│   │       └── media.py               # GET /api/v1/media/{user_id}/{file}
│   ├── db/
│   │   ├── database.py                # aiosqlite Verbindung, init_db(), Default-User
│   │   ├── models.py                  # Pydantic-Modelle: User, Consent, SyncBlob
│   │   └── migrations/
│   │       └── 001_initial.sql        # Schema: users, consents, sync_blobs
│   ├── ingestion/
│   │   ├── photos.py                  # Google Fotos: Sidecar-JSON, Vision, Geocoding
│   │   ├── google_reviews.py          # Google Maps Bewertungen
│   │   ├── google_saved.py            # Google Maps Gespeicherte Orte
│   │   ├── whatsapp.py                # WhatsApp TXT-Export Parser
│   │   ├── signal.py                  # Signal JSON-Export Parser
│   │   └── persons.py                 # Personen-Extraktion aus Nachrichtentext (v0)
│   ├── llm/
│   │   └── connector.py               # LLM-Abstraktion (Ollama/OpenAI/Anthropic)
│   └── rag/
│       ├── embedder.py                # sentence-transformers Embedding-Erzeugung
│       ├── store.py                   # ChromaDB Interface v0 (upsert, query, get)
│       ├── store_v2.py                # ChromaDB Interface v1 (+ user_id-Filter)
│       ├── query_parser.py            # v0: LLM-basierter Query-Parser
│       ├── retriever.py               # v0: RAG-Pipeline mit Klarnamen
│       └── retriever_v2.py            # v1: Token-aware RAG-Pipeline, user-scoped
├── frontend/
│   ├── index.html                     # SPA: Chat, Karte, Import, Einstellungen
│   ├── chat.js                        # Chat-UI, v2 Token-Flow, v0 Fallback
│   ├── map.js                         # Leaflet.js Kartenansicht
│   ├── ner.js                         # Transformers.js NER-Pipeline (WASM)
│   ├── token_store.js                 # IndexedDB Token↔Klarname Wörterbuch
│   └── sync.js                        # Web Crypto AES-GCM Verschlüsselung
├── scripts/
│   └── migrate_to_v2.py               # Einmalige Migration v1→v2 (tokenisiert DB)
├── sample/
│   └── photo_sample.json              # 50 ausgewählte Foto-Dateinamen
├── config.yaml                        # Lokale Konfiguration (nicht in Git)
├── config.yaml.example                # Konfigurationsvorlage
├── requirements.txt                   # Python-Abhängigkeiten
└── start.sh                           # Startskript (venv + uvicorn)
```

---

## Token-Flow

Das zentrale Privacy-Konzept von memosaur v2: persönliche Namen und Orte werden **niemals im Klartext** an den Server gesendet.

### Maskierung (Browser → Server)

```
Nutzereingabe:    "Wo war ich im August mit Nora in München?"
                           │
              NER (Transformers.js, lokal im Browser)
                           │
         Erkannte Entitäten: Nora → PER, München → LOC
                           │
         IndexedDB-Lookup / -Eintrag:
           "Nora"    → PER_1   (neu angelegt)
           "München" → LOC_11  (bereits vorhanden)
                           │
Maskierte Anfrage: "Wo war ich im August mit [PER_1] in [LOC_11]?"
                           │
         POST /api/v1/query
         { masked_query: "...mit [PER_1] in [LOC_11]?",
           person_tokens: ["[PER_1]"],
           location_tokens: ["[LOC_11]"] }
```

### Retrieval (Server)

```
Server empfängt Tokens → ChromaDB-Filter:
  {"$and": [
    {"has_per_1": {"$eq": true}},   ← Boolean-Flag in Metadaten
    {"date_ts": {"$gte": ...}}
  ]}

LLM-Prompt enthält nur Tokens:
  "Kontext: Foto vom 29.08. Ort: [LOC_11]. Personen: [PER_1]..."
  
LLM-Antwort enthält nur Tokens:
  "Am 29.08.2025 warst du mit [PER_1] in [LOC_11]..."
```

### Re-Mapping (Server → Browser)

```
Browser empfängt: "...mit [PER_1] in [LOC_11]..."
                           │
         IndexedDB-Lookup:
           PER_1  → "Nora"
           LOC_11 → "München"
                           │
Anzeige: "...mit Nora in München..."
```

### Token-ID-Format

| Präfix | Typ | Beispiel |
|---|---|---|
| `PER_n` | Person | `[PER_1]` → Nora |
| `LOC_n` | Ort / Location | `[LOC_11]` → München |
| `ORG_n` | Organisation | `[ORG_3]` → Deutsche Post |

---

## Datenmodell

### SQLite (`data/memosaur.db`)

```sql
-- Nutzer (Basis für Multi-User)
users (id TEXT PK, display_name TEXT, created_at INT, is_active INT)

-- DSGVO-Einwilligungen Art. 9
-- scope: 'biometric_photos' | 'gps' | 'messages'
consents (user_id TEXT FK, scope TEXT, granted INT,
          granted_at INT, ip_hint TEXT, PRIMARY KEY(user_id, scope))

-- Verschlüsselte Sync-Blobs
sync_blobs (id INT PK AUTOINCREMENT, user_id TEXT FK,
            device_hint TEXT, blob BLOB, iv TEXT,
            created_at INT, version INT)
```

**Default-User** wird beim ersten Start automatisch angelegt:
- `id`: `00000000-0000-0000-0000-000000000001`
- `display_name`: `ManfredMustermann`
- Alle Consents initial auf `false`

### ChromaDB Collections (v2-Schema)

Alle vier Collections (`photos`, `reviews`, `saved_places`, `messages`) enthalten nach der Migration:

- `user_id` – UUID des Nutzers (für Multi-User-Filterung)
- Alle Texte und String-Metadaten sind **tokenisiert** (Klarnamen durch `[TYPE_n]` ersetzt)
- Boolean-Flags `has_per_1`, `has_loc_2` etc. für strukturierte Filter

#### `photos` – Metadatenfelder

| Feld | Typ | Beschreibung |
|---|---|---|
| `user_id` | string | UUID des Nutzers |
| `source` | string | `"google_photos"` |
| `filename` | string | Originaldateiname |
| `date_ts` | int | Unix-Timestamp |
| `date_iso` | string | ISO-8601 |
| `lat` / `lon` | float | GPS-Koordinaten (nicht tokenisiert) |
| `place_name` | string | Tokenisierter Ortsname, z.B. `[LOC_1]` |
| `persons` | string | Tokenisierte Personen, z.B. `[PER_1],[PER_2]` |
| `has_per_1` | bool | True wenn PER_1 auf dem Foto |
| `has_loc_2` | bool | True wenn LOC_2 relevant |
| `cluster` | string | Geografischer Cluster |

Dokument-Text (tokenisiert):
```
Foto: 20250829_192312.jpg
Datum: 29.08.2025 um 17:23 Uhr
Ort: [LOC_11]
Koordinaten: 48.14021°N, 11.55518°E
Personen: [PER_1]
Bildbeschreibung: Ein kleines Mädchen mit blonden Locken steht auf...
```

#### `messages` – Metadatenfelder

| Feld | Typ | Beschreibung |
|---|---|---|
| `user_id` | string | UUID des Nutzers |
| `source` | string | `"whatsapp"` oder `"signal"` |
| `chat_name` | string | Tokenisierter Chat-Name |
| `date_ts` / `date_iso` | int/string | Zeitstempel |
| `persons` | string | Absender-Tokens |
| `mentioned_persons` | string | Alle erwähnten Personen-Tokens |
| `has_per_1` | bool | True wenn PER_1 im Chunk erwähnt |

---

## Backend-Module

### `backend/db/database.py`

Async SQLite-Verbindung via `aiosqlite`. FastAPI-Dependency `get_db()` liefert eine Connection pro Request.

```python
# FastAPI Startup-Hook
@app.on_event("startup")
async def startup_event():
    await init_db()   # Schema anlegen, Default-User seeden
```

### `backend/llm/connector.py`

Zentrale LLM-Abstraktion. Drei Funktionen:

```python
chat(messages, model=None) -> str
```
Filtert `<think>...</think>`-Blöcke (qwen3 Reasoning-Modus). Provider: `ollama` | `openai` | `anthropic`.

```python
describe_image(image_bytes, prompt=None) -> str
```
- Skaliert Bilder auf max. 768px vor dem Senden (VRAM-Schutz)
- `keep_alive: 0` entlädt das Vision-Modell nach jedem Aufruf aus dem VRAM
- 3 Versuche mit 5/10/15s Pause bei GPU-Timeouts

```python
embed(texts) -> list[list[float]]
```
Immer lokal via `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`, 384 Dim).

### `backend/rag/store_v2.py`

ChromaDB-Interface mit automatischem `user_id`-Filter:

```python
query_collection_v2(col, embeddings, n_results, where, user_id)
# → Fügt {"user_id": {"$eq": user_id}} in die where-Klausel ein
# → Fallback ohne Filter wenn user_id-Feld in alten Docs fehlt

get_all_documents_for_user(col, user_id)
count_documents_for_user(col, user_id)
```

### `backend/rag/retriever_v2.py`

Token-aware RAG ohne LLM-NER (NER findet im Browser statt):

```python
retrieve_v2(masked_query, user_id, person_tokens, location_tokens, ...)
```

Filter-Aufbau aus Token-IDs:
```python
# "[PER_1]" → "has_per_1" → {"has_per_1": {"$eq": True}}
field = "has_" + token.strip("[]").lower()   # "[PER_1]" → "has_per_1"
```

System-Prompt weist LLM explizit an, Tokens unverändert beizubehalten:
> *"Behalte alle Tokens ([PER_n], [LOC_n]) unverändert in deiner Antwort."*

### `backend/api/v1/ingest.py` – Consent-Gate

Foto-Ingestion ist zweistufig:

```
Schritt 1: POST /api/v1/ingest/photos/describe
  → Consent "biometric_photos" prüfen
  → Ollama Vision → Klartext-Beschreibung an Browser zurücksenden

Schritt 2: POST /api/v1/ingest/photos/submit
  → Browser hat Beschreibung lokal maskiert
  → Maskierter Text wird in ChromaDB gespeichert
```

Nachrichten-Ingestion prüft Consent `"messages"` vor dem Upload.

### `backend/api/v1/dictionary.py`

Stellt das Migrations-Wörterbuch bereit:

```
GET  /api/v1/dictionary  → {entries: [...], count: 267}
DELETE /api/v1/dictionary → löscht data/migration_dictionary.json
```

Das Frontend importiert es beim ersten Start automatisch in IndexedDB und ruft dann DELETE auf.

---

## RAG-Pipelines

### v2-Pipeline (Token-Flow)

```
Browser                              Server
  │                                    │
  ├─ NER lokal: "Nora" → [PER_1]      │
  │                                    │
  ├─ POST /api/v1/query ──────────────►│
  │  {masked_query, person_tokens}     │
  │                                    ├─ embed_single(masked_query)
  │                                    ├─ query_collection_v2(where={
  │                                    │    user_id, has_per_1, date_ts
  │                                    │  })
  │                                    ├─ _build_context(sources)
  │                                    ├─ chat(system+context+query)
  │                                    │  → LLM antwortet mit Tokens
  │                                    │
  │◄── {masked_answer, sources} ───────┤
  │                                    │
  ├─ TokenStore.unmaskText(answer)     │
  ├─ _unmaskMetadata(sources)          │
  │                                    │
  └─ Anzeige mit Klarnamen             │
```

### v0-Pipeline (Legacy, Klarnamen)

```
POST /api/query
  → parse_query() [LLM-NER + Regelbasiert]
  → embed_single(query)
  → query_collection(where aus ParsedQuery)
  → chat(context mit Klarnamen)
  → {answer, sources, parsed_query}
```

---

## API-Endpunkte

### v0 (Legacy – Rückwärtskompatibel)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/query` | RAG-Abfrage mit Klarnamen |
| `GET` | `/api/ingest/status` | Dokument-Anzahl |
| `POST` | `/api/ingest/photos` | Fotos einlesen |
| `POST` | `/api/ingest/reviews` | Bewertungen einlesen |
| `POST` | `/api/ingest/saved` | Gespeicherte Orte einlesen |
| `POST` | `/api/ingest/all` | Alle lokalen Quellen |
| `POST` | `/api/ingest/whatsapp` | WhatsApp-Export (multipart) |
| `POST` | `/api/ingest/signal` | Signal-Export (multipart) |
| `GET` | `/api/locations` | GPS-Punkte für Karte |
| `GET` | `/api/media/{filename}` | Bild-Thumbnail |

### v1 (Token-aware, user-scoped)

#### User & Consent

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/v1/users` | Alle Nutzer auflisten |
| `POST` | `/api/v1/users` | Neuen Nutzer anlegen |
| `GET` | `/api/v1/users/{user_id}` | Nutzer-Details |
| `GET` | `/api/v1/consent/{user_id}` | Consent-Status lesen |
| `POST` | `/api/v1/consent/{user_id}` | Consent setzen (Audit-Trail) |

#### Ingestion (mit Consent-Gate)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/v1/ingest/status?user_id=` | Dokument-Anzahl user-scoped |
| `POST` | `/api/v1/ingest/photos/describe` | Schritt 1: Vision-Beschreibung holen |
| `POST` | `/api/v1/ingest/photos/submit` | Schritt 2: Maskiertes Foto speichern |
| `POST` | `/api/v1/ingest/reviews?user_id=` | Bewertungen einlesen |
| `POST` | `/api/v1/ingest/saved?user_id=` | Gespeicherte Orte einlesen |
| `POST` | `/api/v1/ingest/messages` | WhatsApp/Signal (maskierter Text) |

#### Abfrage

| Methode | Pfad | Request | Response |
|---|---|---|---|
| `POST` | `/api/v1/query` | `{user_id, masked_query, person_tokens, location_tokens, ...}` | `{masked_answer, sources, filter_summary}` |

#### Sync & Dictionary

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/v1/dictionary` | Migrations-Wörterbuch abrufen |
| `DELETE` | `/api/v1/dictionary` | Wörterbuch-Datei nach Import löschen |
| `POST` | `/api/v1/sync/{user_id}` | Verschlüsselten Blob hochladen |
| `GET` | `/api/v1/sync/{user_id}` | Neuesten Blob herunterladen |
| `GET` | `/api/v1/sync/{user_id}/history` | Alle Versionen (für Rollback) |

#### Karte & Medien

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/v1/locations?user_id=` | GPS-Punkte user-scoped |
| `GET` | `/api/v1/media/{user_id}/{file}` | Bild-Thumbnail user-scoped |

---

## Frontend-Module

### `frontend/ner.js` – Client-seitige NER

- Modell: `Xenova/bert-base-multilingual-cased-ner-hrl` (~90 MB ONNX)
- Lädt via Transformers.js CDN, gecacht im Browser-Cache nach erstem Download
- `aggregation_strategy: 'simple'` fasst zusammengehörige Tokens zusammen
- Blocking: UI ist bis zum Modellladen gesperrt (Overlay mit Fortschrittsbalken)

```javascript
const { masked, entities } = await NER.maskText("Nora war in München");
// masked:   "[ PER_1] war in [LOC_11]"
// entities: [{word:"Nora", token:"[PER_1]", type:"PER"}, ...]
```

### `frontend/token_store.js` – IndexedDB Wörterbuch

```javascript
// Token vergeben / nachschlagen
await TokenStore.getOrCreateToken("Nora", "PER")   // → "[PER_1]"
await TokenStore.lookupToken("[PER_1]")             // → "Nora"
await TokenStore.unmaskText("Hallo [PER_1]!")       // → "Hallo Nora!"

// Server-Import beim ersten Start
await TokenStore.checkAndImportFromServer()
// → GET /api/v1/dictionary → importTokens() → DELETE /api/v1/dictionary
```

**IndexedDB-Schema:**
```
DB: "memosaur_tokens"
  Store: "dictionary"
    { token_id, cleartext, cleartext_lc, type, first_seen, count }
  Index: cleartext_lc (für Duplikat-Prüfung)
  Index: type (für Zähler pro Typ)
```

### `frontend/sync.js` – Web Crypto Verschlüsselung

```javascript
// Export: Wörterbuch → verschlüsseln → Server
await Sync.exportAndSync(userId, password)
// PBKDF2(password, salt, 250k Iter, SHA-256) → AES-256-GCM Key
// encrypt(JSON.stringify(tokens)) → {blob: base64, iv: base64}
// POST /api/v1/sync/{userId}

// Import: Server → entschlüsseln → IndexedDB
await Sync.importFromSync(userId, password)
// GET /api/v1/sync/{userId} → decrypt(blob, iv) → importTokens()
```

Das Passwort wird **nur in lokalen Variablen** gehalten. Keine Persistenz, kein Server-Transfer.

### `frontend/chat.js` – Query-Flow

```javascript
async function sendQuery() {
  if (window._nerReady) {
    // v2: NER → maskieren → POST /api/v1/query → unmaskieren
    const { masked, entities } = await NER.maskText(query);
    const data = await fetch('/api/v1/query', { body: {masked_query: masked, ...} });
    const unmasked = await TokenStore.unmaskText(data.masked_answer);
    appendAssistantMessage(unmasked, ...);
  } else {
    // v0 Fallback
    const data = await fetch('/api/query', { body: {query} });
    appendAssistantMessage(data.answer, ...);
  }
}
```

---

## Konfiguration

`config.yaml` (aus `config.yaml.example` erstellen, **nicht** in Git):

```yaml
llm:
  provider: ollama          # ollama | openai | anthropic
  base_url: "http://localhost:11434"
  model: "qwen3:8b"         # Text-Modell (Chat + Query-Parser v0)
  vision_model: "gemma3:12b"# Vision für Bildbeschreibungen
  embedding_model: "paraphrase-multilingual-MiniLM-L12-v2"
  # api_key: "sk-..."       # Nur für openai/anthropic

paths:
  takeout_dir: "takeout/Takeout"
  photos_dir: "takeout/Takeout/Google Fotos/Fotos von 2025"
  reviews_file: "takeout/Takeout/Maps (Meine Orte)/Bewertungen.json"
  saved_places_file: "takeout/Takeout/Maps (Meine Orte)/Gespeicherte Orte.json"
  data_dir: "data"           # SQLite + ChromaDB liegen hier

ingestion:
  photo_sample_size: 50      # 0 = alle Fotos
  photo_sample_strategy: "diverse"
  vision_batch_size: 1
  face_recognition_enabled: true

rag:
  top_k: 10
  min_score: 0.3

server:
  host: "0.0.0.0"
  port: 8000
  reload: true
```

---

## Abhängigkeiten

| Paket | Version | Zweck |
|---|---|---|
| `fastapi` | ≥0.111 | Web-Framework |
| `uvicorn[standard]` | ≥0.29 | ASGI-Server |
| `python-multipart` | ≥0.0.9 | Datei-Uploads |
| `aiosqlite` | ≥0.19 | Async SQLite (User, Consent, Sync) |
| `chromadb` | ≥0.5 | Vektordatenbank |
| `sentence-transformers` | ≥3.0 | Lokale Embeddings (multilingual) |
| `ollama` | ≥0.2 | Ollama Python-Client |
| `pyyaml` | ≥6.0 | Konfigurationsdatei |
| `geopy` | ≥2.4 | Reverse Geocoding (Nominatim) |
| `Pillow` | ≥10.3 | Bildverarbeitung, EXIF, Thumbnails |
| `httpx` | ≥0.27 | HTTP-Client |
| `aiofiles` | ≥23.2 | Async Datei-I/O |

**Frontend (CDN, kein Build-Schritt):**

| Bibliothek | Version | Zweck |
|---|---|---|
| Tailwind CSS | CDN | Styling |
| Leaflet.js | 1.9.4 | Interaktive Karte |
| `@xenova/transformers` | 2.17.2 | NER-Modell via WASM im Browser |
