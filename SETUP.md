# memosaur Setup-Anleitung 🦕

Vollständige Installations- und Konfigurationsanleitung für memosaur.

---

## 📋 Inhaltsverzeichnis

1. [Systemvoraussetzungen](#systemvoraussetzungen)
2. [Installation](#installation)
3. [Umgebungsvariablen](#umgebungsvariablen)
4. [Services starten](#services-starten)
5. [Erste Schritte](#erste-schritte)
6. [Troubleshooting](#troubleshooting)

---

## Systemvoraussetzungen

### Software

- **Python**: 3.11+ (mit pyenv empfohlen)
- **Node.js**: 18+ (mit nvm empfohlen)
- **Elasticsearch**: 8.x (für RAG-Suche)
- **SQLite**: 3.x (meist vorinstalliert)

### Optionale Services

- **Ollama**: Für lokale LLM-Inferenz (alternativ: OpenAI/Anthropic/Gemini API)

---

## Installation

### 1. Repository klonen

```bash
git clone <repository-url>
cd memosaur
```

### 2. Python-Umgebung einrichten

```bash
# Virtual Environment erstellen
python3.11 -m venv .venv

# Aktivieren
source .venv/bin/activate  # Linux/macOS
# oder
.venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt
```

### 3. Node.js Dependencies installieren

```bash
npm install
```

### 4. Elasticsearch starten

**Mit Docker:**
```bash
docker run -d \
  --name elasticsearch \
  -p 9200:9200 \
  -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:8.11.0
```

**Oder lokal installieren:**
- Download: https://www.elastic.co/downloads/elasticsearch
- Folge der Installationsanleitung für dein Betriebssystem

**Prüfen:**
```bash
curl http://localhost:9200
# Sollte JSON-Response mit Elasticsearch-Version zurückgeben
```

---

## Umgebungsvariablen

### Option A: `.env` Datei (Empfohlen)

Erstelle eine `.env` Datei im Projekt-Root:

```bash
# /home/bacher/prj/mabrains/memosaur/.env

# === CORS Origins (Optional, für Development) ===
CORS_ORIGINS="http://localhost:8000,http://127.0.0.1:8000"

# === LLM Provider (Optional) ===
# Für externe APIs (statt lokales Ollama):
# OPENAI_API_KEY="sk-..."
# ANTHROPIC_API_KEY="sk-ant-..."
# GEMINI_API_KEY="..."

# === Elasticsearch (Optional, falls nicht localhost) ===
# ELASTICSEARCH_URL="http://localhost:9200"
```

**⚠️ SECURITY**: `.env` sollte in `.gitignore` stehen (ist bereits konfiguriert)!

---

## Services starten

### 1. Backend starten (Python/FastAPI)

```bash
# Im Projekt-Root
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Erwartete Ausgabe:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
21:11:34 [INFO] backend.rag.es_store: ✅ Elasticsearch erreichbar
21:11:34 [INFO] backend.db.database: Initialisiere SQLite-Datenbank
21:11:34 [INFO] backend.main: memosaur v2 gestartet.
INFO:     Application startup complete.
```

**Prüfen:**
```bash
curl http://localhost:8000/health
# {"status":"ok","app":"memosaur","version":"2.0.0"}
```

### 2. WhatsApp Service starten (Node.js)

```bash
# Im Projekt-Root
node index.js
```

**Erwartete Ausgabe:**
```
WhatsApp API listening on http://localhost:3001
WhatsApp-Brücke ist online!
[WhatsApp] Bot-Config geladen: {...}
```

**Beim ersten Start:**
- QR-Code wird angezeigt
- Scanne ihn mit WhatsApp (WhatsApp → Einstellungen → Verknüpfte Geräte)
- Session wird in `.wwebjs_auth/` gespeichert

---

## Erste Schritte

### 1. Browser öffnen

Browser öffnen: http://localhost:8000 — die App startet direkt.

### 2. Daten importieren

memosaur unterstützt verschiedene Datenquellen:

#### Google Takeout (Fotos, Maps)

1. Google Takeout erstellen: https://takeout.google.com
2. Wähle: **Google Fotos**, **Maps (Ihre Orte)**
3. Export als `.zip` herunterladen
4. Entpacke nach `takeout/Takeout/`
5. In memosaur: **Import** → **Google Takeout**

#### WhatsApp Chat-Export

1. WhatsApp öffnen → Chat auswählen → **⋮** → **Mehr** → **Chat exportieren**
2. **Ohne Medien** (nur Text)
3. `.txt` Datei speichern
4. In memosaur: **Import** → **WhatsApp Chat**

### 3. Erste Abfrage

Nach dem Import kannst du natürliche Fragen stellen:

```
"Wo war ich im August mit Sarah?"
"Welche Restaurants habe ich in Berlin besucht?"
"Was hat Tom über das Projekt geschrieben?"
```

---

## Troubleshooting

### Problem: Backend startet nicht - `no such table: schema_migrations`

**Ursache**: Datenbank nicht initialisiert.

**Lösung**:
- Wurde bereits in v2 gefixt
- Falls weiterhin Fehler: `rm data/memosaur.db` und Backend neu starten
- Migrationen werden automatisch angewendet

---

### Problem: `EADDRINUSE: address already in use :::3001`

**Ursache**: WhatsApp-Service läuft bereits auf Port 3001.

**Lösung**:
```bash
# Alten Prozess finden
ps aux | grep "node index.js"

# Prozess beenden (PID aus obigem Befehl)
kill <PID>

# Neu starten
node index.js
```

---

### Problem: Elasticsearch nicht erreichbar

**Ursache**: Elasticsearch läuft nicht oder auf anderem Port.

**Lösung**:
```bash
# Prüfen ob Elasticsearch läuft
curl http://localhost:9200

# Docker Container starten
docker start elasticsearch

# Oder neu starten (siehe Installation)
```

---

### Problem: `Cannot add a UNIQUE column`

**Ursache**: Alte Datenbank-Migration (vor v2 Fix).

**Lösung**:
```bash
# Datenbank sichern
cp data/memosaur.db data/memosaur.db.backup

# Löschen (Migrationen werden neu angewendet)
rm data/memosaur.db

# Backend neu starten
```

---

## Logs prüfen

### Backend-Logs

```bash
tail -f logs/backend.log
```

**Wichtige Log-Meldungen:**
- ✅ `Application startup complete` → Backend läuft
- ✅ `Elasticsearch erreichbar` → RAG-Suche funktioniert
- ✅ `Migration erfolgreich angewendet` → Datenbank OK
- ❌ `ERROR` → Fehler im Log analysieren

### WhatsApp-Logs

```bash
tail -f logs/whatsapp.log
```

**Wichtige Log-Meldungen:**
- ✅ `WhatsApp-Brücke ist online!` → Service läuft
- ✅ `User-Chat-ID: ...` → Bot konfiguriert
- ❌ `ECONNREFUSED 127.0.0.1:8000` → Backend nicht erreichbar

---

## Support & Weitere Hilfe

- **Hauptdokumentation**: [README.md](README.md)
- **Architektur-Details**: [PRODUCT_ANALYSIS.md](PRODUCT_ANALYSIS.md)
- **Antigravity Multi-Agent Setup**: [.antigravity/README.md](.antigravity/README.md)

---

## Sicherheitshinweise

### ⚠️ Für Development (localhost)

- HTTP ist OK für `localhost`

### 🔒 Für Production (deployed)

1. **CORS einschränken**:
   ```bash
   CORS_ORIGINS="https://yourdomain.com"
   ```

2. **Secrets schützen**:
   - `.env` niemals in Git committen
   - Environment Variables auf Server (z.B. systemd, Docker Compose)

---

**🎉 Setup abgeschlossen! memosaur ist jetzt einsatzbereit.**

Bei Fragen oder Problemen: Prüfe die Logs und die Troubleshooting-Sektion oben.
