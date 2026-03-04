# Technische Dokumentation – memosaur

## Inhaltsverzeichnis

1. [Architekturübersicht](#architekturübersicht)
2. [Verzeichnisstruktur](#verzeichnisstruktur)
3. [Datenmodell](#datenmodell)
4. [Backend-Module](#backend-module)
5. [RAG-Pipeline](#rag-pipeline)
6. [API-Endpunkte](#api-endpunkte)
7. [Frontend](#frontend)
8. [Konfiguration](#konfiguration)
9. [Abhängigkeiten](#abhängigkeiten)

---

## Architekturübersicht

```
┌─────────────────────────────────────────────────────────┐
│                  Browser (Frontend)                       │
│     Chat-UI · Karten-Ansicht · Import-UI                 │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / REST
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (Python)                     │
│                                                           │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐  │
│  │  Ingestion   │  │  RAG-Engine │  │  LLM-Connector │  │
│  │  Pipeline    │  │             │  │  (Ollama /     │  │
│  └──────────────┘  └─────────────┘  │  OpenAI / etc) │  │
│                                      └────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                 Lokale Datenhaltung                       │
│                                                           │
│  ┌──────────────────────┐   ┌──────────────────────────┐ │
│  │  ChromaDB            │   │  Dateisystem              │ │
│  │  (Vektordatenbank)   │   │  takeout/ (Originalfotos) │ │
│  │  data/chroma/        │   │  data/                    │ │
│  └──────────────────────┘   └──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Verzeichnisstruktur

```
memosaur/
├── backend/
│   ├── main.py                    # FastAPI-App, Router-Einbindung, Startpunkt
│   ├── api/
│   │   ├── ingest.py              # POST /api/ingest/* – Datenimport-Endpunkte
│   │   ├── query.py               # POST /api/query – RAG-Abfrage
│   │   ├── map.py                 # GET /api/locations – GPS-Punkte für Karte
│   │   └── media.py               # GET /api/media/{filename} – Bild-Thumbnails
│   ├── ingestion/
│   │   ├── photos.py              # Google Fotos: Sidecar-JSON, Vision, Geocoding
│   │   ├── google_reviews.py      # Google Maps Bewertungen
│   │   ├── google_saved.py        # Google Maps Gespeicherte Orte
│   │   ├── whatsapp.py            # WhatsApp TXT-Export Parser
│   │   ├── signal.py              # Signal JSON-Export Parser
│   │   └── persons.py             # Personen-Extraktion aus Nachrichtentext
│   ├── llm/
│   │   └── connector.py           # LLM-Abstraktion (Ollama/OpenAI/Anthropic)
│   └── rag/
│       ├── embedder.py            # sentence-transformers Embedding-Erzeugung
│       ├── store.py               # ChromaDB Interface (upsert, query, get)
│       ├── query_parser.py        # LLM-basierter Query-Parser (Filter-Extraktion)
│       └── retriever.py           # Retrieval + Kontext-Aufbau + LLM-Antwort
├── frontend/
│   ├── index.html                 # Single-Page-App (Tailwind CDN, kein Build)
│   ├── chat.js                    # Chat-UI, Quellenanzeige, Lightbox
│   └── map.js                     # Leaflet.js Kartenansicht
├── sample/
│   └── photo_sample.json          # 50 ausgewählte Foto-Dateinamen (Sample)
├── config.yaml                    # Lokale Konfiguration (nicht eingecheckt)
├── config.yaml.example            # Konfigurationsvorlage
├── requirements.txt               # Python-Abhängigkeiten
└── start.sh                       # Startskript (venv + uvicorn)
```

---

## Datenmodell

### ChromaDB Collections

Alle Dokumente werden in einer von vier Collections gespeichert:

#### `photos`
Jedes Dokument repräsentiert ein einzelnes Foto.

| Feld | Typ | Beschreibung |
|---|---|---|
| `source` | string | `"google_photos"` |
| `filename` | string | Originaldateiname, z.B. `20250829_192312.jpg` |
| `date_ts` | int | Unix-Timestamp der Aufnahme |
| `date_iso` | string | ISO-8601-Datum |
| `lat` / `lon` | float | GPS-Koordinaten |
| `alt` | float | Höhe in Metern |
| `place_name` | string | Ortsname via Reverse Geocoding, z.B. `München, Bayern, Deutschland` |
| `persons` | string | Kommaseparierte Personen-Tags aus Google Fotos, z.B. `Nora,Sarah` |
| `has_nora` | bool | True wenn Nora auf dem Foto erkannt wurde |
| `has_sarah` | bool | True wenn Sarah auf dem Foto erkannt wurde |
| `has_joshua` | bool | True wenn Joshua auf dem Foto erkannt wurde |
| `cluster` | string | Geografischer Cluster-Name aus Sample-Liste |

Dokument-Text-Format:
```
Foto: 20250829_192312.jpg
Datum: 29.08.2025 um 17:23 Uhr
Ort: München, Bayern, Deutschland
Koordinaten: 48.14021°N, 11.55518°E
Personen: Nora
Bildbeschreibung: Auf dem Bild ist ein kleines Mädchen mit blonden Locken...
```

#### `reviews`
Jedes Dokument repräsentiert eine Google Maps Bewertung.

| Feld | Typ | Beschreibung |
|---|---|---|
| `source` | string | `"google_reviews"` |
| `name` | string | Ortsname |
| `address` | string | Adresse |
| `country` | string | Ländercode |
| `date_ts` / `date_iso` | int/string | Datum der Bewertung |
| `lat` / `lon` | float | GPS-Koordinaten |
| `rating` | int | Sternebewertung (1–5) |
| `maps_url` | string | Google Maps URL |

#### `saved_places`
Jedes Dokument repräsentiert einen gespeicherten Google Maps Ort.

Felder analog zu `reviews`, ohne `rating`.

#### `messages`
Jedes Dokument repräsentiert einen Chunk von 10 aufeinanderfolgenden Nachrichten.

| Feld | Typ | Beschreibung |
|---|---|---|
| `source` | string | `"whatsapp"` oder `"signal"` |
| `chat_name` | string | Name des Chats/Kontakts |
| `date_ts` / `date_iso` | int/string | Datum der ersten Nachricht im Chunk |
| `persons` | string | Absender-Namen (kommasepariert) |
| `mentioned_persons` | string | Absender + im Text erwähnte Personen |
| `has_nora` | bool | True wenn Nora im Chunk vorkommt |
| `has_sarah` | bool | True wenn Sarah im Chunk vorkommt |
| `has_joshua` | bool | True wenn Joshua im Chunk vorkommt |

---

## Backend-Module

### `backend/llm/connector.py`

Zentrale Abstraktion für alle LLM-Aufrufe. Drei Funktionen:

```python
chat(messages: list[dict], model: str | None = None) -> str
```
Sendet eine Chat-Anfrage. Filtert automatisch `<think>...</think>`-Blöcke (qwen3).

```python
describe_image(image_bytes: bytes, prompt: str | None = None) -> str
```
Analysiert ein Bild. Skaliert es vor dem Senden auf max. 768px (VRAM-Schutz).
Retry-Logik: 3 Versuche mit 5/10/15s Pause bei GPU-Timeouts.

```python
embed(texts: list[str]) -> list[list[float]]
```
Erzeugt Embeddings via `sentence-transformers` (lokal, kein Ollama-Modell nötig).
Modell: `paraphrase-multilingual-MiniLM-L12-v2` (384 Dimensionen, gecacht).

**Provider-Unterstützung**: `ollama` | `openai` | `anthropic` – konfigurierbar via `config.yaml`.

---

### `backend/rag/query_parser.py`

Extrahiert strukturierte Filter aus natürlichsprachigen Anfragen.

**Zweistufiger Ansatz:**
1. **Regelbasiert** (immer): erkennt Monatsnamen, Jahreszahlen, Keywords für Collections
2. **LLM-basiert**: verfeinert Personen, Orte, relevante Collections

**Output `ParsedQuery`:**
```python
ParsedQuery(
    persons=["Nora"],
    date_from="2025-08-01",
    date_to="2025-08-31",
    relevant_collections=["photos", "messages"],
    metadata_filters={
        "photos": {"$and": [
            {"date_ts": {"$gte": 1754006400}},
            {"date_ts": {"$lte": 1756684799}},
            {"has_nora": {"$eq": True}},
        ]},
        "messages": {"$and": [
            {"date_ts": {"$gte": 1754006400}},
            {"has_nora": {"$eq": True}},
        ]},
    }
)
```

**Personen-Filter-Strategie**: ChromaDB unterstützt kein Substring-Matching.
Daher werden Boolean-Felder (`has_nora`, `has_sarah`, `has_joshua`) als Filter genutzt.
Diese Felder werden bei der Ingestion für alle Collections gesetzt.

---

### `backend/rag/retriever.py`

Vollständige RAG-Pipeline in `answer()`:

```
1. parse_query()     → strukturierte Filter
2. embed_single()    → Query-Embedding
3. query_collection()→ gefiltertes Retrieval pro Collection
4. _build_context()  → Kontext-String mit Quellentyp-Labels
5. chat()            → LLM-Antwort
```

**Adaptive Slot-Vergabe:**
- Relevante Collections (laut Query-Parser): top-2 immer + weitere ab Score 0.20
- Irrelevante Collections: nur ab Score 0.42

---

### `backend/ingestion/photos.py`

Ingestion-Pipeline für Google Fotos:

```
1. Sample-Liste laden (sample/photo_sample.json)
2. Foto aus ZIP oder Ordner laden
3. Sidecar-JSON parsen (GPS, Datum, People-Tags)
4. Reverse Geocoding: GPS → Ortsname (Nominatim, gecacht, 1s Delay)
5. Vision-LLM: Bildbeschreibung auf Deutsch (768px-Resize vorher)
6. Personen-Flags setzen (has_nora, has_sarah, has_joshua)
7. Embedding erzeugen
8. In ChromaDB speichern
```

---

### `backend/ingestion/persons.py`

Personen-Extraktion für Nachrichten-Chunks:

```
1. Bekannte Personen aus Foto-Metadaten laden (gecacht)
2. Einfacher String-Match: bekannte Namen im Text suchen
3. Heuristik: unbekannte großgeschriebene Wörter finden
4. LLM-Extraktion nur wenn potenzielle unbekannte Namen gefunden
```

---

### `backend/api/media.py`

Thumbnail-Auslieferung mit In-Memory-Cache:

- Sucht Bild zuerst im extrahierten Ordner, dann in ZIP-Archiven
- Erstellt JPEG-Thumbnails: `thumb` (300px), `full` (1200px)
- EXIF-Rotation wird korrigiert
- Cache: max. 200 Einträge (LRU-ähnlich)

---

## RAG-Pipeline

```
Nutzer-Anfrage
      │
      ▼
┌─────────────────┐
│  Query-Parser   │ ← LLM-Aufruf #1 (schnell, ~1-2s)
│  (query_parser) │   Extrahiert: Personen, Datum, Collections
└────────┬────────┘
         │ ParsedQuery mit Filtern
         ▼
┌─────────────────┐
│    Embedder     │ ← sentence-transformers (lokal, ~50ms)
│  (embedder.py)  │   384-dimensionaler Vektor
└────────┬────────┘
         │ Query-Embedding
         ▼
┌─────────────────┐
│  ChromaDB       │ ← Cosine-Similarity + Metadaten-Filter
│  (store.py)     │   Pro Collection: top-6 mit where-Klausel
└────────┬────────┘
         │ Relevante Dokumente + Scores
         ▼
┌─────────────────┐
│  Kontext-Aufbau │   Max. 12 Quellen, mit Typ-Labels und Metadaten
│  (retriever.py) │
└────────┬────────┘
         │ Strukturierter Kontext
         ▼
┌─────────────────┐
│   LLM-Antwort   │ ← LLM-Aufruf #2 (Hauptantwort, ~5-30s)
│  (connector.py) │   System-Prompt + Kontext + Frage
└────────┬────────┘
         │ Antwort + Quellenliste
         ▼
      Nutzer
```

---

## API-Endpunkte

### Ingestion

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/ingest/status` | Anzahl indexierter Dokumente pro Collection |
| `POST` | `/api/ingest/photos` | 50 Sample-Fotos einlesen |
| `POST` | `/api/ingest/reviews` | Google Maps Bewertungen einlesen |
| `POST` | `/api/ingest/saved` | Gespeicherte Orte einlesen |
| `POST` | `/api/ingest/all` | Alle lokalen Quellen einlesen |
| `POST` | `/api/ingest/whatsapp` | WhatsApp-Export hochladen (multipart) |
| `POST` | `/api/ingest/signal` | Signal-Export hochladen (multipart) |
| `GET` | `/api/ingest/stream/{source}` | SSE-Fortschrittsstream |

Query-Parameter für alle POST-Endpunkte: `?reset=true` leert die Collection vor dem Import.

### Abfrage

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/query` | RAG-Abfrage mit LLM-Antwort |

Request-Body:
```json
{
  "query": "Wo war ich im August mit Nora?",
  "collections": null,
  "n_results": 6,
  "min_score": 0.2,
  "date_from": null,
  "date_to": null
}
```

Response:
```json
{
  "query": "...",
  "answer": "...",
  "sources": [...],
  "source_count": 8,
  "parsed_query": {
    "persons": ["Nora"],
    "date_from": "2025-08-01",
    "date_to": "2025-08-31",
    "relevant_collections": ["photos", "messages"],
    "filter_summary": "Personen: Nora · Zeitraum: August 2025"
  }
}
```

### Karte & Medien

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/locations` | Alle GPS-Punkte für Kartenansicht |
| `GET` | `/api/media/{filename}` | Bild-Thumbnail (`?size=thumb` oder `?size=full`) |
| `GET` | `/api/config` | Aktuelle (nicht-sensitive) Konfiguration |
| `GET` | `/health` | Healthcheck |
| `GET` | `/docs` | Swagger UI (automatisch generiert) |

---

## Frontend

Drei Tabs in einer Single-Page-App (`frontend/index.html`), kein Build-Schritt nötig.

### Chat (`frontend/chat.js`)

- Sendet Anfragen an `POST /api/query`
- Zeigt erkannte Filter als Chips (Personen, Zeitraum, Orte)
- Rendert Quellen nach Typ:
  - **Fotos**: Thumbnail + Metadaten + Bildbeschreibung, klickbar für Lightbox
  - **Bewertungen**: Ortsname, Sterne, Rezensions-Blockquote
  - **Nachrichten**: Chat-Blasen mit Zeitstempel, scrollbar
- Lightbox: Vollbild mit Datum/Ort/Personen-Untertitel, ESC zum Schließen

### Karte (`frontend/map.js`)

- Lädt Daten von `GET /api/locations`
- Leaflet.js mit OpenStreetMap-Tiles
- Farbkodierte Marker: blau (Fotos), grün (Bewertungen), amber (Orte)
- Popups mit Name, Datum, Adresse, Google Maps Link
- Automatisches Zoom auf alle Marker

### Import (`frontend/index.html` + `chat.js`)

- Buttons für lokale Quellen (`/api/ingest/all` etc.)
- Datei-Upload für WhatsApp/Signal
- Datenbank-Statusanzeige

---

## Konfiguration

Alle Einstellungen in `config.yaml` (aus `config.yaml.example` erstellen):

```yaml
llm:
  provider: ollama          # ollama | openai | anthropic
  base_url: "http://..."    # Ollama-Adresse
  model: "qwen3:8b"         # Text-Modell
  vision_model: "gemma3:12b"# Vision-Modell
  embedding_model: "..."    # Wird nicht mehr für Ollama genutzt
  # api_key: "sk-..."       # Nur für openai/anthropic

paths:
  takeout_dir: "takeout/Takeout"
  photos_dir: "takeout/Takeout/Google Fotos/Fotos von 2025"
  reviews_file: "takeout/Takeout/Maps (Meine Orte)/Bewertungen.json"
  saved_places_file: "takeout/Takeout/Maps (Meine Orte)/Gespeicherte Orte.json"
  data_dir: "data"

ingestion:
  photo_sample_size: 50
  photo_sample_strategy: "diverse"   # diverse | newest | all
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
| `chromadb` | ≥0.5 | Vektordatenbank |
| `sentence-transformers` | ≥3.0 | Lokale Embeddings |
| `ollama` | ≥0.2 | Ollama Python-Client |
| `pyyaml` | ≥6.0 | Konfigurationsdatei |
| `geopy` | ≥2.4 | Reverse Geocoding |
| `Pillow` | ≥10.3 | Bildverarbeitung, Thumbnails |
| `httpx` | ≥0.27 | HTTP-Client |
| `aiofiles` | ≥23.2 | Asynchrones Datei-I/O |

Alle Abhängigkeiten in `requirements.txt`.
