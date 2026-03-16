# Memosaur — Implementierte Applikations-Features

Stand: 16.03.2026 | Branch: `main`

## 1. Daten-Ingestion

### 1.1 WhatsApp Chat-Import (TXT-Export)
- Datei-Upload: WhatsApp TXT-Exportdateien (Android + iOS Format) hochladen und parsen
- Multi-Pattern-Parser: Erkennt beide WhatsApp-Exportformate
- System-Message-Filter: Automatisches Herausfiltern von `<Medien weggelassen>` etc.
- Mehrzeilige Nachrichten: Korrekte Zusammenführung
- Endpoint: `POST /api/v1/ingest/messages` mit `source_type=whatsapp`

### 1.2 WhatsApp Live-Ingestion (Bridge)
- Echtzeit-Erfassung: Jede ein- und ausgehende WhatsApp-Nachricht wird live in ChromaDB indiziert
- Deduplizierter Bulk-Import: `POST /api/whatsapp/import-all-chats` mit Smart Deduplication
- Selektiver Import: `POST /api/whatsapp/import-selected-chats`
- Rate Limiting: 3s Pause zwischen Chats, 60s Batch-Pause nach je 10 Chats
- Exponential Backoff: Automatische Wiederholung bei WhatsApp-Rate-Limits
- Import-Tracking: Pro-Chat Timestamp-Tracking in ChromaDB

### 1.3 Signal Messenger Import
- JSON-Export-Parser: Signal Desktop Backup (messages.json) importieren
- Endpoint: `POST /api/v1/ingest/messages` mit `source_type=signal`

### 1.4 Google Fotos
- Google Takeout Import: Fotos aus extrahierten Ordnern oder ZIP-Archiven
- Sidecar-JSON Parsing: GPS-Koordinaten, Datum und People-Tags aus Google-Metadaten
- Vision-LLM Bildbeschreibung: Automatische KI-Beschreibung jedes Fotos
- Reverse Geocoding: GPS-Koordinaten via Nominatim/OSM in lesbare Ortsnamen
- Sampling-Strategien: `diverse`, `newest`, `all`

### 1.5 Google Maps Bewertungen
- Takeout Import: `Bewertungen.json` parsen und indexieren
- Endpoint: `POST /api/v1/ingest/reviews`

### 1.6 Google Maps Gespeicherte Orte
- Takeout Import: `Gespeicherte Orte.json` parsen und indexieren
- Endpoint: `POST /api/v1/ingest/saved`

### 1.7 Ingestion-Status
- Dokument-Zähler: Anzahl indexierter Dokumente pro Collection
- Endpoint: `GET /api/v1/ingest/status`

---

## 2. Chat / RAG Pipeline

### 2.1 Streaming RAG (v3)
- Real-Time Streaming: Server-Sent Events mit Wort-für-Wort-Ausgabe
- 5-Phasen-Pipeline: Query-Parsing, Hybrid-Retrieval, Context Compression, Prompt-Bau, LLM-Streaming
- SSE-Event-Typen: `query_id`, `query_analysis`, `retrieval`, `thought`, `text`, `sources`, `error`
- Chat-Historie: Session-basierte Konversationshistorie
- Abbruch-Funktion: Laufende Queries per AbortController abbrechen
- Endpoint: `POST /api/v1/query_stream`

### 2.2 Thinking Mode (Researcher/Challenger/Decider)
- Dreistufige Analyse-Pipeline: Researcher -> Challenger -> Decider
- Aktives Nachforschen: Re-Retrieval mit neuen Parametern bei "continue"-Entscheidung
- Max. 10 Iterationen (konfigurierbar)
- SSE-Events: `thinking_start`, `researcher`, `challenger`, `decider`, `retrieval_focus`, `thinking_end`

### 2.3 Query-Parsing (LLM-basiert)
- Strukturierte Filter-Extraktion: Personen, Datum/Zeitraum, Orte aus natürlicher Sprache
- Temporale Auflösung: "letztes Wochenende", "im August" etc.
- ChromaDB where-Filter: Automatische Generierung von Metadaten-Filtern

### 2.4 Hybrid-Retrieval
- Semantische Suche: Embedding-basiert (paraphrase-multilingual-MiniLM-L12-v2)
- Keyword-Suche: Ergänzende exakte Textsuche
- Multi-Collection: Parallele Suche über `messages`, `photos`, `reviews`, `saved_places`
- Deduplizierung: Semantische + Keyword-Ergebnisse automatisch dedupliziert

### 2.5 Cross-Encoder Re-Ranking
- Modell: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (multilingual, lokal)
- "Lost in the Middle"-Mitigierung
- Graceful Fallback bei Ladefehler

### 2.6 Context Window Management
- Token-Budget: Intelligente Verwaltung des LLM Context Window
- Tiktoken-Integration: Präzise Token-Zählung
- Context Compression: 50 Quellen von ~6k auf ~2k Tokens komprimierbar

### 2.7 Temporal Fuzzy Expansion
- Mehrere Zeiträume parallel mit abnehmender Confidence

### 2.8 WhatsApp Bot (Selbst-Chat)
- RAG via WhatsApp: Fragen im eigenen Selbst-Chat stellen
- 4-Stufen-Sicherheit: Bot-Aktivierung, User-Chat-ID, Selbst-Chat-Prüfung, Test-Mode
- Loop Prevention: Bot-Antworten werden nicht erneut verarbeitet
- Webhook: `POST /api/v1/webhook`

---

## 3. Gesichtserkennung / Entity Resolution

### 3.1 Face Detection + Embedding
- MediaPipe Face Detection mit Bounding Boxes
- FaceNet Embedding: 512-dimensionale Face-Embeddings (VGGFace2)
- AMD GPU Support: DirectML-Beschleunigung (Fallback: CPU)

### 3.2 DBSCAN Clustering
- Automatisches Clustering via DBSCAN (Cosine Similarity)
- Konfigurierbare Parameter: `eps`, `min_samples`
- Cluster-Vorschläge mit repräsentativen Bildern

### 3.3 Entity Linking (Human-in-the-Loop)
- Cluster-zu-Person-Verknüpfung
- Chat-Alias-Verknüpfung: Personen mit WhatsApp-Chat-Identifiern verbinden
- Foto-Sync: Metadaten automatisch aktualisiert nach Verknüpfung

### 3.4 Entity-Verwaltung
- Umbenennung, Entknüpfung, Split-Analyse und -Ausführung

### 3.5 Label-Validierung (Ground Truth)
- Validierungs-Sessions mit Qualitätsmetriken
- Actions: validate, reject, split, merge
- Ground Truth Export als JSON

---

## 4. Speech-to-Text (STT)

### 4.1 Whisper-Transkription
- Modell: faster-whisper (large-v3, Fallback: medium, small)
- Automatische Spracherkennung (DE/EN etc.)
- CPU/GPU konfigurierbar

### 4.2 Sprachnachrichten-Pipeline
- Automatische Erkennung aller WhatsApp-Sprachnachrichten
- LLM-Zusammenfassung: Transkript -> 1-3 Sätze (3. Person)
- ChromaDB-Indexierung als Nachricht

---

## 5. LLM-Abstraktion

### 5.1 Multi-Provider Support
- Ollama (lokal, Fallback), Gemini (aktuell aktiv: gemini-2.5-flash), OpenAI, Anthropic

### 5.2 Funktionen
- Chat, Chat-Streaming, Vision (Bildbeschreibung), Embedding

---

## 6. Kartenansicht

- Leaflet.js Karte: GPS-Punkte aus Fotos, Reviews, Saved Places
- Farbcodierte Marker: Blau (Fotos), Grün (Reviews), Amber (Saved Places)
- Filter nach Quelle und Datum

---

## 7. Qualitätssicherung / Testing

### 7.1 Query Logging
- Vollständiger RAG-Trace in SQLite (`query_logs.db`)
- Eindeutige Query-IDs, Source-Snapshots für hermetic Replay

### 7.2 Semantische Evaluation
- Drei Methoden: `embedding_only`, `llm_judge`, `combined`
- Verdicts: PASS, PARTIAL, FAIL
- Required/Forbidden Facts, Golden Answers

### 7.3 Replay / Modellvergleich
- Hermetic Replay, Integration Replay, Batch-Vergleich

---

## 8. User-Verwaltung
- CRUD-Endpoints: Erstellen, Lesen, Auflisten, Profil-Update
- Default-User: `ManfredMustermann` wird beim ersten Start angelegt
- Endpoint: `GET/POST/PATCH /api/v1/users`

---

## 9. Infrastruktur
- **config.yaml**: Zentrale Konfiguration für LLM, Pfade, RAG, ES, STT, FaceRec
- **Docker**: docker-compose.yaml, Dockerfile (Backend + WhatsApp Bridge)
- **start.sh**: Startet Backend (Port 8000) + WhatsApp Bridge (Port 3001)
- **Media-Serving**: Thumbnails (300px), Full-Size (1200px), Bounding-Box-Crop, LRU-Cache
- **Frontend-Serving**: FastAPI serviert `/static/`, SPA Root

---

## Zusammenfassung

| Kategorie | Details |
|-----------|---------|
| Ingestion-Quellen | 7 (WhatsApp TXT, WhatsApp Live, Signal, Google Fotos, Reviews, Saved Places, STT) |
| RAG-Subsysteme | 8 (Streaming, Thinking Mode, Query-Parsing, Hybrid-Retrieval, Re-Ranking, Context, Temporal, Bot) |
| Gesichtserkennung | 5 Bereiche (Detection, Clustering, Linking, Entity-Mgmt, Validation) |
| LLM Provider | 4 (Ollama, Gemini, OpenAI, Anthropic) |
| ChromaDB Collections | 5 (`messages`, `photos`, `reviews`, `saved_places`, `faces`) |
| REST API Endpoints | ~50+ |
| Frontend Tabs | 4 (Chat, Personen, Validierung, Karte) |
