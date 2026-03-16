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

## Q&A: Multi-Agent Setup (.antigravity)

**Q: Was ist `.antigravity/`?**
A: Konfigurationsordner für das **Antigravity Manager View** Multi-Agent-System. Jede `.md`-Datei definiert einen spezialisierten Agenten mit Rolle, Kontext, Domain und Verhalten.

**Q: Welche Agenten gibt es?**

| Agent | Datei | Trigger | Modell |
|-------|-------|---------|--------|
| BD (Product Manager) | `bd.md` | Neue Business-Anforderungen, PRD | Sonnet Thinking |
| UX Manager | `ux.md` | UI/UX-Änderungen, Wireframes | Sonnet Standard |
| Architect | `architect.md` | Technisches Planen, System Design | Sonnet Thinking |
| WhatsApp-Dev | `whatsapp-dev.md` | WhatsApp Import, Bot, Bridge | Sonnet Standard |
| Face-Recognition-Dev | `face-recognition-dev.md` | Fotos, Gesichter, Clustering | Sonnet Standard |
| Chat-RAG-Dev | `chat-rag-dev.md` | Chat UI, RAG Pipeline, LLM | Sonnet Standard |
| Developer | `developer.md` | Infrastruktur, Config, allgemein | Sonnet Standard |
| Tester | `tester.md` | Tests schreiben und ausführen | Sonnet Standard |
| QS | `qs.md` | Bug-Koordination, Log-Analyse | Sonnet Thinking |
| Scribe | `scribe.md` | Dokumentation nach Feature-Abschluss | Sonnet Standard |
| Prompt-Engineer | `prompt-engineer.md` | Prompt-Optimierung | Sonnet Standard |

**Q: Welchen Developer-Agenten soll ich wählen?**
A: Faustregel:
- WhatsApp / Import / Bot → `@whatsapp-dev`
- Gesichter / Fotos / Personen → `@face-recognition-dev`
- Chat / Suche / LLM / RAG → `@chat-rag-dev`
- Alles andere (Config, Media, Infra) → `@developer`

**Q: Was sind globale Agent-Regeln?**
A: Siehe `.antigravity/rules.md`. Kernpunkte: Immer existierenden Code lesen bevor schreiben, niemals ohne Bestätigung löschen/überschreiben, kleine fokussierte Änderungen bevorzugen, bei Unklarheit fragen.

**Q: In welcher Reihenfolge sollen Agenten aufgerufen werden?**
A:
1. (Optional) `@bd` → PRD, User Stories
2. (Optional) `@ux` → User Flows, Wireframes
3. `@architect` → Technischer Plan (Pflicht vor Implementierung)
4. Passender `@*-dev` → Implementierung nach Freigabe
5. `@tester` → Tests schreiben und ausführen
6. `@qs` → Qualitätsprüfung (bei Bugs immer zuerst!)
7. `@scribe` → Dokumentation

**Q: Bug gefunden — was tun?**
A: Immer `@qs [Bug-Beschreibung]` — QS koordiniert Analyse, Fix und Verifikation.

**Q: Welche Agenten kann ich parallel laufen lassen?**
A: Sinnvolle Kombinationen: `BD + UX`, `Tester + Scribe`, `WhatsApp-Dev + Face-Recognition-Dev`, `Chat-RAG-Dev + Developer`.

**Nicht parallel:** Architect + Developer am gleichen Feature, zwei Devs auf derselben Datei, `WhatsApp-Dev + Developer` auf `backend/main.py`.

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
| `.antigravity/README.md` | Multi-Agent Setup Übersicht |
| `.antigravity/rules.md` | Globale Agent-Regeln |
