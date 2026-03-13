# 2nd Memory Setup-Anleitung 🦕

Vollständige Installations- und Konfigurationsanleitung für 2nd Memory.

---

## 📋 Inhaltsverzeichnis

1. [Systemvoraussetzungen](#systemvoraussetzungen)
2. [Installation](#installation)
3. [OAuth-Konfiguration (Google Sign-In)](#oauth-konfiguration-google-sign-in)
4. [Umgebungsvariablen](#umgebungsvariablen)
5. [Services starten](#services-starten)
6. [Erste Schritte](#erste-schritte)
7. [Troubleshooting](#troubleshooting)

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
cd 2nd-memory
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

## OAuth-Konfiguration (Google Sign-In)

2nd-memory verwendet **Google OAuth 2.0** für die Authentifizierung. Ohne diese Konfiguration erhalten User beim Login den Fehler:

```
Fehler 401: invalid_client
```

### Schritt 1: Google Cloud Console öffnen

1. Gehe zu: https://console.cloud.google.com
2. **Neues Projekt erstellen** (oder bestehendes wählen):
   - Name: `2nd-memory` (oder beliebig)
   - Projekt-ID wird automatisch generiert

### Schritt 2: OAuth Consent Screen konfigurieren

1. **APIs & Services** → **OAuth consent screen**
2. **User Type**: `Internal` (nur für Google Workspace) oder `External`
3. **App-Informationen**:
   - App name: `2nd-memory`
   - User support email: Deine E-Mail
   - Developer contact: Deine E-Mail
4. **Scopes**: Standard (keine zusätzlichen Scopes nötig)
5. **Test users** (bei External): Deine E-Mail hinzufügen
6. **Speichern**

### Schritt 3: OAuth 2.0 Credentials erstellen

1. **APIs & Services** → **Credentials** → **+ CREATE CREDENTIALS**
2. Wähle: **OAuth client ID**
3. **Application type**: `Web application`
4. **Name**: `2nd-memory-oauth`
5. **Authorized JavaScript origins**:
   ```
   http://localhost:8000
   http://127.0.0.1:8000
   ```

   **Für Production** (falls deployed):
   ```
   https://yourdomain.com
   ```

6. **Authorized redirect URIs**:
   ```
   http://localhost:8000/api/auth/google/callback
   ```

   **Für Production**:
   ```
   https://yourdomain.com/api/auth/google/callback
   ```

7. **CREATE** klicken

### Schritt 4: Client ID & Secret kopieren

Nach der Erstellung wird ein Popup angezeigt:

```
Your Client ID
123456789-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com

Your Client Secret
GOCSPX-xyz123abc456def789
```

**⚠️ WICHTIG**: Client Secret sicher aufbewahren! Er wird nur einmal angezeigt.

---

## Umgebungsvariablen

### Option A: `.env` Datei (Empfohlen)

Erstelle eine `.env` Datei im Projekt-Root:

```bash
# /home/user/prj/2nd-memory/.env

# === Google OAuth (PFLICHT für Login) ===
GOOGLE_CLIENT_ID="123456789-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="GOCSPX-xyz123abc456def789"
OAUTH_REDIRECT_URI="http://localhost:8000/api/auth/google/callback"

# === Frontend URL ===
FRONTEND_URL="http://localhost:8000"

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

### Option B: Export in Shell (Temporär)

```bash
export GOOGLE_CLIENT_ID="123456789-abc...apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="GOCSPX-xyz123..."
export OAUTH_REDIRECT_URI="http://localhost:8000/api/auth/google/callback"
```

**Nachteil**: Muss bei jedem Terminal-Neustart wiederholt werden.

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
21:11:34 [INFO] backend.main: 2nd-memory v2 gestartet.
INFO:     Application startup complete.
```

**Prüfen:**
```bash
curl http://localhost:8000/health
# {"status":"ok","app":"2nd-memory","version":"2.0.0"}

curl http://localhost:8000/api/auth/config
# {"google_client_id":"123456...","oauth_configured":true,"passkey_enabled":false}
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

### 1. Login testen

1. Browser öffnen: http://localhost:8000
2. Du wirst zu `/login.html` redirected
3. Klick auf **"Mit Google anmelden"**
4. Google OAuth-Popup öffnet sich
5. Wähle deinen Google-Account
6. Nach erfolgreichem Login: Redirect zu `/` (Hauptseite)

### 2. Daten importieren

2nd-memory unterstützt verschiedene Datenquellen:

#### Google Takeout (Fotos, Maps)

1. Google Takeout erstellen: https://takeout.google.com
2. Wähle: **Google Fotos**, **Maps (Ihre Orte)**
3. Export als `.zip` herunterladen
4. Entpacke nach `takeout/Takeout/`
5. In 2nd-memory: **Import** → **Google Takeout**

#### WhatsApp Chat-Export

1. WhatsApp öffnen → Chat auswählen → **⋮** → **Mehr** → **Chat exportieren**
2. **Ohne Medien** (nur Text)
3. `.txt` Datei speichern
4. In 2nd-memory: **Import** → **WhatsApp Chat**

### 3. Erste Abfrage

Nach dem Import kannst du natürliche Fragen stellen:

```
"Wo war ich im August mit Marie?"
"Welche Restaurants habe ich in Berlin besucht?"
"Was hat Thomas über das Projekt geschrieben?"
```

---

## Troubleshooting

### Problem: `Fehler 401: invalid_client` beim Login

**Ursache**: Google OAuth Credentials nicht konfiguriert oder falsch.

**Lösung**:
1. Prüfe `.env` Datei: `GOOGLE_CLIENT_ID` und `GOOGLE_CLIENT_SECRET` gesetzt?
2. Prüfe Backend-Log beim Start:
   ```bash
   curl http://localhost:8000/api/auth/config
   # Sollte zeigen: "oauth_configured": true
   ```
3. Prüfe Google Cloud Console:
   - Authorized JavaScript origins korrekt? (`http://localhost:8000`)
   - Authorized redirect URIs korrekt? (`http://localhost:8000/api/auth/google/callback`)
4. Backend neu starten (lädt `.env` beim Start)

---

### Problem: `GET /login.html` → 404 Not Found

**Ursache**: Backend-Route fehlt (sollte in v2 behoben sein).

**Lösung**:
- Prüfe `backend/main.py` Zeile ~139: Route `/login.html` existiert?
- Backend neu starten mit `--reload`

---

### Problem: Backend startet nicht - `no such table: schema_migrations`

**Ursache**: Datenbank nicht initialisiert.

**Lösung**:
- Wurde bereits in v2 gefixt
- Falls weiterhin Fehler: `rm data/2nd-memory.db` und Backend neu starten
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
cp data/2nd-memory.db data/2nd-memory.db.backup

# Löschen (Migrationen werden neu angewendet)
rm data/2nd-memory.db

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
- ✅ `Migration 002 erfolgreich angewendet` → Datenbank OK
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
- OAuth redirect URIs: `http://localhost:8000/...`

### 🔒 Für Production (deployed)

1. **HTTPS ist PFLICHT**:
   ```
   FRONTEND_URL="https://yourdomain.com"
   OAUTH_REDIRECT_URI="https://yourdomain.com/api/auth/google/callback"
   ```

2. **Google Cloud Console**:
   - Authorized origins: `https://yourdomain.com`
   - Redirect URIs: `https://yourdomain.com/api/auth/google/callback`

3. **Cookies auf `secure` setzen**:
   - In `backend/auth/oauth.py` Zeile ~185:
     ```python
     secure=True,  # HTTPS erforderlich
     ```

4. **CORS einschränken**:
   ```bash
   CORS_ORIGINS="https://yourdomain.com"
   ```

5. **Secrets schützen**:
   - `.env` niemals in Git committen
   - Environment Variables auf Server (z.B. systemd, Docker Compose)

---

**🎉 Setup abgeschlossen! 2nd-memory ist jetzt einsatzbereit.**

Bei Fragen oder Problemen: Prüfe die Logs und die Troubleshooting-Sektion oben.
