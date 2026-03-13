# Technische Dokumentation – 2nd Memory v2

## Inhaltsverzeichnis

1. [Architekturübersicht](#architekturübersicht)
2. [Verzeichnisstruktur](#verzeichnisstruktur)
3. [Entity-Resolution (Human-in-the-Loop)](#entity-resolution-human-in-the-loop)
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
│  ┌─────────────────┐  ┌─────────────────────┐                    │
│  │   IndexedDB     │  │  Web Crypto API     │                    │
│  │  Entity-Mapping │  │  AES-GCM Encrypt    │                    │
│  │  Wörterbuch     │  │  für Sync-Blob      │                    │
│  └──────┬──────────┘  └──────────┬──────────┘                    │
│         │                        │                               │
└─────────┼────────────────────────┼───────────────────────────────┘
          │ POST /api/v1/query     │ POST /sync
          ▼                        ▼ 
┌──────────────────────────────────────────────────────────────────┐
│              FastAPI Backend – /api/v0/ + /api/v1/               │
│                                                                    │
│  /v1/query  /v1/ingest  /v1/sync  /v1/consent  /v1/entities    │
│                                                                    │
│  ┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐  │
│  │   ChromaDB   │   │  SQLite          │   │  Ollama          │  │
│  │   / ES       │   │  users           │   │  qwen3:8b Chat   │  │
│  │              │   │  consents        │   │  gemma3:12b      │  │
│  │  user-scoped │   │  sync_blobs      │   │  Vision          │  │
│  └──────────────┘   └──────────────────┘   └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

Zwei API-Generationen laufen parallel:
- **v0** (`/api/*`): Original-API mit Klarnamen, bleibt für Rückwärtskompatibilität erhalten.
- **v1** (`/api/v1/*`): Aktuelle API (user-scoped, DSGVO-konform).

---

## Verzeichnisstruktur

```
2nd-memory/
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
│   │       ├── ingest.py              # POST /api/v1/ingest/* (Consent-Gate)
│   │       ├── query.py               # POST /api/v1/query (user-scoped)
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
│       └── retriever_v2.py            # v1: Agentic RAG-Pipeline, user-scoped
├── frontend/
│   ├── index.html                     # SPA: Chat, Karte, Import, Einstellungen
│   ├── chat.js                        # Chat-UI, v2 Entity-Flow, v0 Fallback
│   ├── map.js                         # Leaflet.js Kartenansicht
│   ├── entities.js                    # Entity-Management & Personen-Onboarding
│   └── sync.js                        # Web Crypto AES-GCM Verschlüsselung
├── scripts/
│   └── ...
├── sample/
│   └── photo_sample.json              # 50 ausgewählte Foto-Dateinamen
├── config.yaml                        # Lokale Konfiguration (nicht in Git)
├── config.yaml.example                # Konfigurationsvorlage
├── requirements.txt                   # Python-Abhängigkeiten
└── start.sh                           # Startskript (venv + uvicorn)
```

---

## Entity-Resolution (Human-in-the-Loop)

Das zentrale Privacy-Konzept von 2nd Memory v2: persönliche Namen und Orte werden lokal verarbeitet und verknüpft.

### Entity-Mapping

Anstatt Namen im Browser zu maskieren, nutzt 2nd-memory jetzt ein integriertes Entity-Resolution-System:

1. **Gesichtserkennung**: Beim Import von Fotos werden Gesichter erkannt und lokal geclustert (via DBSCAN).
2. **Onboarding**: Im "Personen"-Tab kann der Nutzer diese Cluster einem Namen (z.B. "Anna") und optional einer Chat-ID zuweisen.
3. **Internal Mapping**: Das System speichert diese Verknüpfung in der lokalen Browser-DB (IndexedDB) und synchronisiert sie verschlüsselt.

### RAG-Retrieval

Beim Abfragen der Daten nutzt der Agent Tools, um gezielt in den verschiedenen Datenquellen zu suchen:

- **search_photos**: Sucht nach Clustern oder Personennamen in den Foto-Metadaten.
- **search_messages**: Sucht in den (lokal indexierten) Chatverläufen.
- **search_places**: Sucht in Google Maps Daten.

Der Privacy-Aspekt wird dadurch gewahrt, dass die gesamte Anwendung (Backend + Datenbank + LLM) **privat und lokal** auf der Hardware des Nutzers läuft. Es gibt keinen Cloud-Server, der die Daten im Klartext sieht.

---

## Datenmodell

### SQLite (`data/2nd-memory.db`)

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
- Alle Texte und String-Metadaten werden lokal indexiert
- Boolean-Flags `has_per_1`, `has_loc_2` etc. für strukturierte Filter

#### `photos` – Metadatenfelder

| Feld | Typ | Beschreibung |
|---|---|---|
| `user_id` | string | UUID des Nutzers |
| `source` | string | `"google_photos"` |
| `filename` | string | Originaldateiname |
| `date_ts` | int | Unix-Timestamp |
| `date_iso` | string | ISO-8601 |
| `lat` / `lon` | float | GPS-Koordinaten |
| `place_name` | string | Ortsname (Klartext) |
| `persons` | string | Zugeordnete Personen (Namen) |
| `entity_ids` | string | IDs der verknüpften Personen |
| `cluster` | string | Geografischer Cluster |

Dokument-Text (indexiert):
```
Foto: 20250829_192312.jpg
Datum: 29.08.2025 um 17:23 Uhr
Ort: München, Marienplatz
Koordinaten: 48.14021°N, 11.55518°E
Personen: Anna
Bildbeschreibung: Ein kleines Mädchen mit blonden Locken steht auf...
```

#### `messages` – Metadatenfelder

| Feld | Typ | Beschreibung |
|---|---|---|
| `user_id` | string | UUID des Nutzers |
| `source` | string | `"whatsapp"` oder `"signal"` |
| `chat_name` | string | Name des Chats |
| `date_ts` / `date_iso` | int/string | Zeitstempel |
| `sender` | string | Absender (Name/ID) |
| `mentioned_persons` | string | Alle erwähnten Personen |

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

Agentic RAG mit Tool-Einsatz:

```python
retrieve_v2(query, user_id, ...)
```

Die Suche erfolgt quellenübergreifend. Der Agent entscheidet, welche Tools (`search_photos`, `search_messages`, etc.) mit welchen Parametern (Personennamen, Orte, Zeiträume) aufgerufen werden.

### `backend/api/v1/ingest.py` – Consent-Gate

Foto-Ingestion ist zweistufig:

```
Schritt 1: POST /api/v1/ingest/photos/describe
  → Consent "biometric_photos" prüfen
  → Ollama Vision → Bildbeschreibung generieren

Schritt 2: POST /api/v1/ingest/photos/submit
  → Metadaten und Beschreibung werden in ChromaDB gespeichert
```

Nachrichten-Ingestion prüft Consent `"messages"` vor dem Upload.

### `backend/api/v1/entities.py`

Verwaltet das Entity-Mapping (Personen-Onboarding):

```
GET  /api/entities/list  → Liste der verknüpften Personen
POST /api/entities/link  → Cluster einer Person zuordnen
```

---

## RAG-Pipelines

### v2-Pipeline (Agentic RAG)

```
Browser                              Server
  │                                    │
  ├─ POST /api/v1/query ──────────────►│
  │  {query, user_id}                  │
  │                                    ├─ Agent analysiert Anfrage
  │                                    ├─ Tool-Calls (z.B. search_photos)
  │                                    ├─ Retrieval (ES / ChromaDB)
  │                                    ├─ _build_context(sources)
  │                                    ├─ chat(system+context+query)
  │                                    │
  │◄── {answer, sources} ──────────────┤
  │                                    │
  └─ Anzeige                           │
```

### v0-Pipeline (Legacy)

```
POST /api/query
  → parse_query() [LLM-NER + Regelbasiert]
  → embed_single(query)
  → query_collection(where aus ParsedQuery)
  → chat(context)
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

### v1 (Current – user-scoped, GDPR compliant)

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
| `POST` | `/api/v1/ingest/photos/submit` | Schritt 2: Foto-Metadaten speichern |
| `POST` | `/api/v1/ingest/reviews?user_id=` | Bewertungen einlesen |
| `POST` | `/api/v1/ingest/saved?user_id=` | Gespeicherte Orte einlesen |
| `POST` | `/api/v1/ingest/messages` | WhatsApp/Signal (Klartext-Import) |

#### Abfrage

| Methode | Pfad | Request | Response |
|---|---|---|---|
| `POST` | `/api/v1/query` | `{user_id, query, ...}` | `{answer, sources, filter_summary}` |

#### Sync & Dictionary

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/v1/sync/{user_id}` | Verschlüsselten Blob hochladen |
| `GET` | `/api/v1/sync/{user_id}` | Neuesten Blob herunterladen |
| `GET` | `/api/v1/sync/{user_id}/history` | Alle Versionen (für Rollback) |

#### Karte & Medien

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/v1/locations?user_id=` | GPS-Punkte user-scoped |
| `GET` | `/api/v1/media/{user_id}/{file}` | Bild-Thumbnail user-scoped |

#### Webhook (v1)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/v1/webhook` | WhatsApp-Nachricht empfangen & beantworten |

---

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
