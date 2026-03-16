# ChromaDB → Elasticsearch — Migrationsstatus

Stand: 2026-03-16 | Branch: `main`

---

## Abgeschlossene Migrations-Phasen

| Phase | Beschreibung | Status |
|-------|-------------|--------|
| 1 | ES-Store (`es_store.py`) implementiert, alle Kernindices erstellt | Abgeschlossen |
| 2 | Ingestion-Pipeline auf ES umgestellt (messages, photos, reviews, saved_places) | Abgeschlossen |
| 3 | RAG-Retrieval auf ES umgestellt (`retriever_v3.py`, `retriever_v3_stream.py`) | Abgeschlossen |
| 4 | Streaming + Thinking Mode auf ES-Retrieval migriert | Abgeschlossen |
| 5 | Cleanup: requirements.txt, docker-compose, CLAUDE.md, FEATURES.md | Abgeschlossen |

---

## Offene Reste — noch ChromaDB

### `faces`-Collection

**Betroffene Dateien:**

| Datei | Art der ChromaDB-Nutzung |
|-------|--------------------------|
| `backend/ingestion/faces.py` | `upsert_documents` — Gesichts-Embeddings speichern |
| `backend/ingestion/persons.py` | `get_all_documents` — alle Gesichter laden für DBSCAN-Clustering |
| `backend/api/v1/entities.py` | `get_collection` — Gesichter lesen/updaten (Entity Linking) |
| `backend/api/v1/validation.py` | `get_collection` — Ground-Truth-Sessions, Validierungsstatus schreiben |
| `backend/rag/store.py` | Direkter `import chromadb` — ChromaDB-Client, Hilfsfunktionen |
| `backend/rag/store_v2.py` | `from backend.rag.store import ...` — erbt ChromaDB-Client |
| `backend/rag/retriever.py` | `from backend.rag.store import ...` — Legacy-Retriever (nicht aktiv) |
| `backend/scripts/reprocess_faces.py` | `get_collection` — Batch-Reprocessing |
| `backend/scripts/migrate_to_unified_ids.py` | `get_collection` — Einmalig-Migrationsskript |
| `backend/scripts/migrate_txt_imports.py` | `get_collection` — Einmalig-Migrationsskript |
| `backend/config/whatsapp_import.py` | `get_collection` — Import-Tracking per Chat |

### Warum noch ChromaDB?

Die Gesichtserkennung (`faces`) nutzt ChromaDB als Spezial-Speicher für 512-dimensionale
FaceNet-Embeddings. Die ChromaDB-API bietet hier direkten Collection-Zugriff mit
Metadaten-Filtern, der für DBSCAN-Clustering und inkrementelles Entity-Linking nötig ist.
Eine ES-Migration erfordert Anpassung des Clustering-Algorithmus und der Label-Validation-Pipeline —
das ist eigenständige Arbeit für den `@face-recognition-dev`-Agenten.

Der WhatsApp-Import-Tracker in `backend/config/whatsapp_import.py` nutzt ChromaDB ebenfalls
noch für per-Chat-Timestamp-Tracking — das ist ein kleines, isoliertes Überbleibsel.

---

## Nächste Schritte (Phase 6 — Owner: @face-recognition-dev)

1. Elasticsearch-Index `faces` mit `dense_vector`-Mapping anlegen (512 Dimensionen)
2. `backend/ingestion/faces.py` auf `es_store.upsert_documents` umstellen
3. `backend/ingestion/persons.py`: DBSCAN-Clustering auf ES-Scroll-API umstellen
4. `backend/api/v1/entities.py` + `validation.py`: `get_collection` → ES-Queries ersetzen
5. `backend/config/whatsapp_import.py`: Import-Tracking in SQLite oder ES-Dokument umziehen
6. `backend/rag/store.py` und `store_v2.py` als deprecated markieren oder entfernen
7. `chromadb>=0.5.0` in `requirements.txt` reaktivieren bis Phase 6 abgeschlossen, dann entfernen

---

## Hinweis: requirements.txt

`chromadb` ist in `requirements.txt` auskommentiert. Solange `faces`-Domain noch ChromaDB
nutzt, muss das Paket für einen vollständigen Funktionsumfang installiert sein:

```bash
pip install chromadb>=0.5.0
```

Nach Abschluss von Phase 6 kann diese Zeile endgültig entfernt werden.
