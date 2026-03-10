# 🔐 Authentication-System – Setup Guide

## Übersicht

memosaur nutzt jetzt **Google OAuth 2.0** für sichere Authentifizierung. Das System ist als **Single-User-Installation** konzipiert: Der erste Google-Account, der sich anmeldet, wird zum Owner – weitere Accounts werden abgewiesen.

## ✅ Was wurde implementiert?

### Backend
- ✅ **DSGVO-Consent entfernt** (obsolet, da alles lokal läuft)
- ✅ **Google OAuth 2.0** Integration (`backend/auth/oauth.py`)
- ✅ **Session-Management** mit HttpOnly-Cookies (`backend/auth/session.py`)
- ✅ **Auth-Middleware** für geschützte Routen (`backend/middleware/auth.py`)
- ✅ **DB-Migration** (002_auth.sql) mit Users-Erweiterung & Sessions-Tabelle
- ✅ **Feature-Flag** `AUTH_ENABLED` für Development ohne Login

### Frontend
- ✅ **Login-Seite** (`frontend/login.html`) mit Google Sign-In Button
- ✅ **Session-Check** in `index.html` (redirect zu Login wenn nicht authentifiziert)
- ✅ **Logout-Button** in Settings

### Features
- ✅ **Single-User-Constraint**: Nur ein Google-Account pro Installation
- ✅ **30-Tage-Sessions**: Automatisches Re-Login unnötig
- ✅ **Sicheres Logout**: Session-Löschung & Cookie-Invalidierung

## 🚀 Setup (Google OAuth)

### 1. Google Cloud Console

1. Gehe zu: https://console.cloud.google.com/apis/credentials
2. Erstelle ein neues Projekt (z.B. "memosaur-auth")
3. Aktiviere "Google+ API" (falls nicht schon aktiv)
4. Navigiere zu **Credentials** → **Create Credentials** → **OAuth 2.0 Client IDs**
5. **Application type**: Web application
6. **Name**: memosaur
7. **Authorized redirect URIs**:
   ```
   http://localhost:8000/api/auth/google/callback
   ```
8. Kopiere **Client ID** und **Client Secret**

### 2. Environment Variables

Erstelle `.env` aus `.env.example`:

```bash
cp .env.example .env
```

Fülle die OAuth-Credentials ein:

```bash
# .env
GOOGLE_CLIENT_ID=your-actual-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-actual-secret

# Development: Auth deaktivieren (kein Login nötig)
AUTH_ENABLED=false

# Production: Auth aktivieren
# AUTH_ENABLED=true
```

### 3. Dependencies installieren

```bash
pip install google-auth>=2.27.0
```

Oder komplette Requirements:

```bash
pip install -r requirements.txt
```

### 4. Datenbank-Migration

Beim nächsten `./start.sh` werden die Migrationen automatisch angewendet:

```bash
./start.sh
```

Die Migration `002_auth.sql` fügt folgende Tabellen hinzu:
- `users` wird erweitert mit `google_id`, `email`, `picture_url`
- Neue Tabelle: `sessions`
- Neue Tabelle: `passkey_credentials` (für zukünftiges Passkey-Feature)

## 🧪 Testing

### Development-Modus (ohne Login)

Setze in `.env`:

```bash
AUTH_ENABLED=false
```

→ Kein Login nötig, System nutzt Default-User `ManfredMustermann`

### Production-Modus (mit Login)

Setze in `.env`:

```bash
AUTH_ENABLED=true
GOOGLE_CLIENT_ID=your-real-id
GOOGLE_CLIENT_SECRET=your-real-secret
```

1. Öffne http://localhost:8000
2. → Redirect zu `/login.html`
3. Klick auf "Mit Google anmelden"
4. Google OAuth Flow
5. → Redirect zurück zu `/` (eingeloggt)

### Logout testen

1. Gehe zu **Settings-Tab**
2. Klick auf "🚪 Abmelden"
3. → Redirect zu `/login.html`

## 🔧 Architektur

### Backend Flow

```
1. User klickt "Sign in with Google" (Frontend)
   ↓
2. Google OAuth Flow → JWT-Credential
   ↓
3. Frontend POST /api/auth/google/token { credential: "..." }
   ↓
4. Backend verifiziert JWT mit Google
   ↓
5. Backend prüft:
   - Existiert bereits ein User?
   - Falls ja: Ist es der gleiche Google-Account?
   - Falls nein: Erstelle neuen User
   ↓
6. Backend erstellt Session (30 Tage Expiry)
   ↓
7. Backend setzt HttpOnly-Cookie: memosaur_session=...
   ↓
8. Frontend redirect zu /
```

### Session-Validierung

```
Jeder API-Request:
  ↓
1. Middleware liest Cookie: memosaur_session
   ↓
2. Lookup Session in DB
   ↓
3. Prüfe Expiry (< 30 Tage?)
   ↓
4. Gib user_id zurück
   ↓
5. API-Handler nutzt: user_id = Depends(get_current_user_id)
```

## 📁 Neue Dateien

### Backend
```
backend/
  auth/
    __init__.py
    oauth.py          # Google OAuth 2.0 Flow
    session.py        # Session CRUD
  middleware/
    __init__.py
    auth.py           # Auth-Middleware (Depends)
  db/
    migrations/
      002_auth.sql    # Auth-Schema
```

### Frontend
```
frontend/
  login.html          # Login-Seite
```

### Geänderte Dateien
```
backend/
  main.py             # Auth-Router registriert, Consent-Router entfernt
  db/database.py      # Migrations-System
  db/models.py        # Consent-Models entfernt
  api/v1/users.py     # Consent-Erstellung entfernt

frontend/
  index.html          # Consent-Modal entfernt, Auth-Check hinzu

requirements.txt      # google-auth dependency
.env.example          # OAuth Env-Vars
```

## ⚠️ Bekannte Einschränkungen

1. **Single-User only**: Kein Multi-User-Support (by Design)
2. **Nur Google OAuth**: Andere Provider (GitHub, Microsoft) noch nicht implementiert
3. **Passkey TODO**: WebAuthn/Passkey-Support vorbereitet aber nicht fertig
4. **HTTP in Dev**: Cookies mit `secure=False` (in Production: `secure=True` für HTTPS)

## 🛠️ Troubleshooting

### "Google OAuth not configured"

**Problem**: `GOOGLE_CLIENT_ID` fehlt in `.env`

**Lösung**:
```bash
# .env
GOOGLE_CLIENT_ID=your-id.apps.googleusercontent.com
```

### "Dieses System ist bereits registriert"

**Problem**: Versuch, mit anderem Google-Account einzuloggen (Single-User-Constraint)

**Lösung**: Entweder:
1. Nutze den ursprünglichen Account
2. Lösche DB und starte neu: `rm data/memosaur.db && ./start.sh`

### Session läuft nicht ab

**Problem**: Sessions bleiben 30 Tage gültig

**Lösung**: Cleanup-Job läuft automatisch bei `/api/auth/status` – alte Sessions werden gelöscht

### Frontend zeigt "Not authenticated" trotz Login

**Problem**: Cookie wird nicht gesetzt

**Check**:
1. Browser DevTools → Application → Cookies
2. Sollte `memosaur_session` sichtbar sein
3. Falls nicht: Backend-Logs prüfen

## 🔮 Roadmap (Optional)

- [ ] **Passkey/WebAuthn**: Passwordless Auth als Alternative zu Google
- [ ] **GitHub OAuth**: Zweiter OAuth-Provider
- [ ] **Remember Me**: Längere Sessions (90 Tage) opt-in
- [ ] **Security Audit**: Professionelles Security-Review

## 📚 Weitere Infos

- Google OAuth Docs: https://developers.google.com/identity/protocols/oauth2
- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
- WebAuthn/Passkey: https://webauthn.guide/
