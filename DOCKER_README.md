# 🐳 memosaur Docker Setup

**Privacy-First Personal Memory System** – Deployment mit Docker Compose

---

## 🚀 Quick Start (5 Minuten)

```bash
# 1. Repository clonen
git clone https://github.com/yourusername/memosaur.git
cd memosaur

# 2. Environment vorbereiten
cp .env.example .env
cp config.yaml.example config.yaml

# 3. Ollama installieren (lokal auf Host-Maschine)
# macOS/Linux: https://ollama.com/download
# Windows: https://ollama.com/download
ollama pull phi4
ollama pull gemma3:12b

# 4. Docker-Compose starten
docker-compose up -d

# 5. Browser öffnen
open http://localhost:8000
```

**Fertig!** 🎉 memosaur läuft jetzt lokal.

---

## 📋 Voraussetzungen

### System Requirements

- **OS**: Linux, macOS, Windows (mit WSL2)
- **RAM**: Mindestens 8GB (16GB empfohlen für Ollama + Docker)
- **Disk**: 10GB+ frei (Modelle + Daten)
- **Docker**: Version 20.10+
- **Docker Compose**: Version 2.0+

### Software Dependencies

1. **Docker & Docker Compose**
   - Linux: https://docs.docker.com/engine/install/
   - macOS: https://docs.docker.com/desktop/install/mac-install/
   - Windows: https://docs.docker.com/desktop/install/windows-install/

2. **Ollama** (lokal auf Host, nicht in Docker)
   - https://ollama.com/download
   - Warum lokal? Performance + GPU-Support

---

## 🏗️ Architektur

```
┌─────────────────────────────────────────────────────────┐
│                     Host Machine                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Ollama (Port 11434)  ← GPU-beschleunigte Modelle      │
│    ├─ phi4 (14B)         - RAG + Chat                  │
│    └─ gemma3:12b (12B)   - Vision (Bilder)             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                    Docker Compose                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │ backend (Port 8000)                               │ │
│  │ - FastAPI                                         │ │
│  │ - Python 3.11                                     │ │
│  │ - RAG Logic                                       │ │
│  │ - Frontend Serving                                │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │ chromadb (Port 8001)                              │ │
│  │ - Vector Database                                 │ │
│  │ - Embeddings Storage                              │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │ whatsapp (Port 3001)                              │ │
│  │ - Node.js                                         │ │
│  │ - whatsapp-web.js                                 │ │
│  │ - QR-Code Auth                                    │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 Konfiguration

### 1. Environment Variables (`.env`)

```bash
cp .env.example .env
nano .env
```

**Wichtigste Einstellungen**:

```bash
# CORS (für Production anpassen)
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# Ollama Host (Docker → Host)
OLLAMA_HOST=http://host.docker.internal:11434

# WhatsApp (optional)
WHATSAPP_BOT_ENABLED=false
WHATSAPP_USER_CHAT_ID=

# ⚠️  PRIVACY: Externe APIs (NICHT empfohlen)
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=
```

### 2. LLM Configuration (`config.yaml`)

```bash
cp config.yaml.example config.yaml
nano config.yaml
```

```yaml
llm:
  provider: ollama
  base_url: "http://localhost:11434"  # Host-Maschine
  model: "phi4"                       # RAG + Chat
  vision_model: "gemma3:12b"          # Bildbeschreibungen
```

**⚠️  PRIVACY WARNING**: Nutze NUR `provider: ollama` (lokal)!
Externe APIs (OpenAI, Anthropic, Gemini) senden deine Daten an Drittanbieter.

---

## 📦 Services

### Backend (`memosaur-backend`)

**FastAPI Backend** – Hauptanwendung

- **Port**: 8000
- **Health**: http://localhost:8000/health
- **Docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:8000

**Volumes**:
- `./data:/app/data` – SQLite DB, ChromaDB, Uploads
- `./config.yaml:/app/config.yaml:ro` – Konfiguration (read-only)
- `./frontend:/app/frontend:ro` – Static Files (read-only)

**Logs**:
```bash
docker-compose logs -f backend
```

### ChromaDB (`memosaur-chromadb`)

**Vector Database** – Embeddings für RAG

- **Port**: 8001 (intern: 8000)
- **Health**: http://localhost:8001/api/v1/heartbeat
- **Persistent**: `./data/chroma:/chroma/chroma`

**Logs**:
```bash
docker-compose logs -f chromadb
```

### WhatsApp Bridge (`memosaur-whatsapp`)

**Node.js Bot** – Live WhatsApp Integration

- **Port**: 3001
- **Status**: http://localhost:3001/api/whatsapp/status
- **QR-Code**: http://localhost:3001/api/whatsapp/qr
- **Persistent**: `./.wwebjs_auth:/app/.wwebjs_auth`

**Logs**:
```bash
docker-compose logs -f whatsapp
```

---

## 🚦 Commands

### Start Services

```bash
# All services
docker-compose up -d

# Specific service
docker-compose up -d backend

# With logs
docker-compose up
```

### Stop Services

```bash
# Stop all
docker-compose stop

# Stop specific
docker-compose stop backend

# Stop + Remove containers
docker-compose down
```

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Rebuild

```bash
# Rebuild all
docker-compose build

# Rebuild specific service
docker-compose build backend

# Rebuild + Start
docker-compose up -d --build
```

### Shell Access

```bash
# Backend shell
docker-compose exec backend bash

# WhatsApp shell
docker-compose exec whatsapp sh
```

### Database

```bash
# SQLite Shell
docker-compose exec backend python -m sqlite3 /app/data/memosaur.db

# Database Backup
docker-compose exec backend tar -czf /app/data/backup.tar.gz /app/data/memosaur.db
```

---

## 🔍 Troubleshooting

### Problem: Backend startet nicht

**Symptom**: `docker-compose logs backend` zeigt Fehler

**Lösungen**:
1. **Ollama läuft nicht**
   ```bash
   ollama serve  # In separatem Terminal starten
   curl http://localhost:11434/api/tags  # Testen
   ```

2. **Modelle fehlen**
   ```bash
   ollama pull phi4
   ollama pull gemma3:12b
   ```

3. **Port 8000 bereits belegt**
   ```bash
   lsof -i :8000  # macOS/Linux
   # Port in docker-compose.yml ändern: "8080:8000"
   ```

### Problem: ChromaDB Connection Error

**Symptom**: Backend kann ChromaDB nicht erreichen

**Lösung**:
```bash
# ChromaDB Status prüfen
docker-compose ps chromadb
curl http://localhost:8001/api/v1/heartbeat

# Neu starten
docker-compose restart chromadb
```

### Problem: WhatsApp QR-Code wird nicht angezeigt

**Symptom**: `/api/whatsapp/qr` gibt 404

**Lösung**:
```bash
# Logs prüfen
docker-compose logs whatsapp

# Session löschen und neu starten
rm -rf .wwebjs_auth/
docker-compose restart whatsapp

# QR-Code abrufen
curl http://localhost:3001/api/whatsapp/qr
```

### Problem: "Permission Denied" beim Start

**Symptom**: Container kann nicht auf Volumes zugreifen

**Lösung** (Linux):
```bash
# Rechte setzen
sudo chown -R $USER:$USER data/ .wwebjs_auth/

# SELinux (falls aktiviert)
chcon -Rt svirt_sandbox_file_t data/ .wwebjs_auth/
```

### Problem: Out of Memory (OOM)

**Symptom**: Container crasht, Docker-Desktop zeigt 100% RAM

**Lösung**:
```bash
# Docker RAM-Limit erhöhen (Docker Desktop Settings)
# macOS/Windows: Settings → Resources → Memory → 8GB+

# Alternativ: Kleineres Modell nutzen
# In config.yaml: model: "qwen3:4b" (statt phi4)
```

---

## 🔐 Security Best Practices

### 1. Secrets Management

❌ **NIEMALS**:
- API Keys in `config.yaml` committen
- `.env` ins Git einchecken
- Sensitive Daten in Dockerfiles

✅ **IMMER**:
- `.env` für Secrets nutzen
- `config.yaml` in `.gitignore`
- ENV-Variablen in docker-compose.yml

### 2. CORS Configuration

**Development** (Localhost):
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

**Production** (Self-Hosted):
```bash
CORS_ORIGINS=https://memosaur.yourdomain.com
```

### 3. Network Isolation

Alle Services laufen im `memosaur` Docker Network:
- Nur exposedte Ports sind öffentlich erreichbar
- Inter-Service Communication über interne DNS-Namen

### 4. Non-Root User

Alle Container laufen als Non-Root User (`memosaur:1000`):
```dockerfile
RUN useradd -m -u 1000 memosaur
USER memosaur
```

### 5. Health Checks

Alle Services haben Health Checks → Auto-Restart bei Failures

---

## 🧪 Testing

### Health Checks

```bash
# Backend
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# ChromaDB
curl http://localhost:8001/api/v1/heartbeat
# Expected: {"nanosecond heartbeat": ...}

# WhatsApp
curl http://localhost:3001/api/whatsapp/status
# Expected: {"status": "ready", ...}
```

### API Tests

```bash
# User erstellen
curl -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Test User"}'

# RAG Query
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Was habe ich letztes Jahr gemacht?"}'
```

---

## 📈 Production Deployment

### 1. Nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/memosaur
server {
    listen 80;
    server_name memosaur.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/memosaur /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 2. HTTPS mit Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d memosaur.yourdomain.com
```

### 3. Systemd Service (Auto-Start)

```bash
# /etc/systemd/system/memosaur.service
[Unit]
Description=memosaur Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/memosaur
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable memosaur
sudo systemctl start memosaur
```

### 4. Backups

```bash
# Backup Script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
tar -czf /backup/memosaur_$DATE.tar.gz \
  data/ \
  .wwebjs_auth/ \
  config.yaml \
  .env

# Cronjob (täglich um 3 Uhr)
0 3 * * * /opt/memosaur/backup.sh
```

---

## 🆙 Updates

### Update Docker Images

```bash
# Pull latest images
docker-compose pull

# Rebuild custom images
docker-compose build --no-cache

# Restart mit neuen Images
docker-compose up -d
```

### Update Code

```bash
cd memosaur
git pull origin main
docker-compose build backend whatsapp
docker-compose up -d
```

---

## 🐛 Development

### Local Development (ohne Docker)

```bash
# Backend
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# WhatsApp Bridge
node index.js
```

### Hot-Reload in Docker

```yaml
# docker-compose.override.yml (nur Development)
version: '3.8'
services:
  backend:
    volumes:
      - ./backend:/app/backend  # Code-Mounting
    environment:
      - ENVIRONMENT=development
    command: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
docker-compose up  # Lädt override automatisch
```

---

## 📚 Related Docs

- [Installation Guide](README.md)
- [Profile Management](docs/PROFILE_MANAGEMENT.md)
- [Authentication Roadmap](PRODUCT_ANALYSIS.md)
- [API Documentation](http://localhost:8000/docs)

---

## 🆘 Support

**Issues**: https://github.com/yourusername/memosaur/issues
**Docs**: https://docs.memosaur.com (TBD)
**Discord**: https://discord.gg/memosaur (TBD)

---

**Status**: ✅ Production-Ready (Single-User Self-Hosted)
**Version**: 2.0.0
**Last Updated**: 2026-03-10
