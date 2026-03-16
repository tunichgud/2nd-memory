# CLAUDE.md — Memosaur Project Guide

## Was ist Memosaur?

Memosaur ist ein persönliches Gedächtnis-System: es importiert WhatsApp-Chats, Fotos, Google Maps-Daten und ermöglicht per Chat (RAG + LLM) das Durchsuchen dieser Erinnerungen.

**Stack:**
- **Backend:** Python (FastAPI) unter `backend/`
- **WhatsApp Bridge:** Node.js (Express + whatsapp-web.js) — `index.js`
- **Frontend:** HTML/JS unter `frontend/`
- **Vektordatenbank:** ChromaDB
- **KI:** Claude Sonnet (Anthropic API)

---

## Q&A: Projekt-Basics

**Q: Wie starte ich das Projekt?**
A: `./start.sh` startet Backend + WhatsApp Bridge. Backend läuft auf Port 8000, WhatsApp Bridge auf Port 3001.

**Q: Wo liegt die Konfiguration?**
A: `config.yaml` für alle LLM-, RAG- und Pfad-Einstellungen. Secrets (API-Keys) in `.env`. Niemals API-Keys hardcoden — immer `process.env` (Node) oder `os.environ` / python-dotenv (Python).

**Q: Wo ist was im Backend?**
A:
- `backend/main.py` — FastAPI App, Routers, CORS
- `backend/api/v1/` — REST Endpoints (webhook, entities, media, validation)
- `backend/rag/` — RAG Pipeline (retriever_v2.py, store.py)
- `backend/ingestion/` — Import-Logik (photos.py, google_maps.py)
- `backend/llm/` — LLM Provider-Abstraktion

**Q: Welche ChromaDB-Collections gibt es?**
A: `messages`, `photos`, `reviews`, `saved_places` — immer lowercase, plural.

**Q: Welche API-Conventions gelten?**
A: Alle Endpoints unter `/api/v1/`. CORS erlaubt localhost:8001 (Frontend) und localhost:3001 (WhatsApp Bridge). Health-Check: `GET /health`.

---

## Q&A: Code-Stil

**Q: Node.js oder Python — welche Konventionen?**
A:
- **Node.js:** `async/await`, funktionaler Stil (`map/filter/reduce`), named exports, `try/catch` mit typed errors, JSDoc auf allen exports.
- **Python:** Type hints überall, Pydantic-Models statt raw dicts, `pathlib` statt `os.path`, Google-style docstrings.
- **Beide:** Kein `console.log`/`print` in Production — Logger verwenden. Max. 40 Zeilen pro Funktion.

**Q: Wie sollen Dateinamen aussehen?**
A: Node.js Module → `camelCase.js`, Routes → `kebab-case.js`, Python → `snake_case.py`, Tests → `*.test.js` / `test_*.py`, Docs → `UPPER_CASE.md`.

**Q: Welches Commit-Format?**
A: Conventional Commits — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`.

---

## Q&A: Wichtige File-Ownership

**Q: Wer darf welche Dateien anfassen?**
A:

| Datei / Bereich | Owner-Agent |
|-----------------|-------------|
| `backend/main.py` | Developer (koordiniert mit anderen) |
| `backend/api/v1/webhook.py`, `backend/rag/` | Chat-RAG-Dev |
| `backend/ingestion/whatsapp*`, `index.js` | WhatsApp-Dev |
| `backend/ingestion/photos.py` | Developer |
| `backend/api/v1/entities.py` | Face-Recognition-Dev |
| `config.yaml`, `start.sh` | Developer |
| `frontend/chat.js` | Chat-RAG-Dev |
| `frontend/index.html` | Developer (Layout) / Chat-RAG-Dev (Chat-Tab) |

---

## Q&A: Testing & Qualität

**Q: Wo liegen Tests?**
A: `tests/` — Python-Tests mit pytest (`test_*.py`), JS-Tests mit `*.test.js`.

**Q: Was muss vor einem Merge grün sein?**
A: Alle Tests in `tests/`. Der Tester blockiert bei roten Tests — nichts merged ohne grüne Tests.

**Q: Wie laufen die Tests?**
A: Python: `pytest tests/` — Node.js: `npm test` (falls konfiguriert).

---

## Q&A: Deployment & Infrastruktur

**Q: Gibt es Docker-Support?**
A: Ja — `docker-compose.yaml` + `Dockerfile` (Backend) + `Dockerfile.whatsapp` (WhatsApp Bridge). Dokumentation in `DOCKER_README.md`.

**Q: Wo werden Daten gespeichert?**
A: `data/photos/` (Originale), `data/thumbnails/` (300px), ChromaDB unter `chroma_db/` bzw. `chromadb_data/`.

---

## Weitere Dokumentation

| Datei | Inhalt |
|-------|--------|
| `INSTALL.md` | Installation & Setup |
| `SETUP.md` | Erste Schritte |
| `DOCKER_README.md` | Docker-Setup |
| `docs/ARCHITECTURE_DECISIONS.md` | Architekturentscheidungen |
| `docs/STREAMING_ARCHITECTURE.md` | Streaming-Implementierung |
