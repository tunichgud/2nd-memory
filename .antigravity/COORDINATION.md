# 🏗️ Team-Koordination: OAuth Implementation & Dependency Management

**Datum:** 2026-03-10
**Status:** 🔴 BLOCKIERT - Server startet nicht
**Teams:** OAuth-Team & Dependency-Team

---

## 🎯 Aktuelle Situation

### ✅ Erfolgreich implementiert

1. **OAuth `.env` Loading Fix** (OAuth-Team)
   - ✅ `load_dotenv()` in [backend/main.py:19-28](../backend/main.py#L19-L28) hinzugefügt
   - ✅ `python-dotenv>=1.0.0` zu requirements.txt hinzugefügt
   - ✅ ENV-Variablen werden nun korrekt geladen
   - ✅ `passlib[bcrypt]>=1.7.4` hinzugefügt und installiert

2. **Auth Router Integration** (OAuth-Team)
   - ✅ OAuth Router in main.py registriert
   - ✅ Local Auth Router in main.py registriert
   - ✅ Neue Auth-Module unter `backend/auth/` erstellt

### 🔴 Blockierende Probleme

1. **Fehlende Dependencies**
   ```
   ModuleNotFoundError: No module named 'elasticsearch'
   ```

   **Ursache:** `elasticsearch>=8.12.0` ist in requirements.txt definiert, aber **nicht installiert**

   **Betroffene Module:**
   - `backend/api/v1/entities.py` (Zeile 18)
   - `backend/rag/es_store.py` (Zeile 11)

2. **Parallele Entwicklungsarbeit**
   - Es läuft gerade eine parallele Entwicklung
   - Risk von Merge-Konflikten in requirements.txt und main.py

---

## 📋 Koordinationsplan

### Phase 1: Dependency Synchronisation (JETZT)

**Verantwortlich:** Dependency-Team

1. ✅ **Bereits installiert:**
   - `passlib==1.7.4`
   - `python-dotenv==1.2.2`

2. ⚠️ **Noch zu installieren:**
   ```bash
   pip install elasticsearch>=8.12.0 elasticsearch-dsl>=8.12.0
   ```

3. 📝 **Action Item:**
   ```bash
   # Koordiniert mit paralleler Entwicklung
   pip install -r requirements.txt --upgrade
   ```

### Phase 2: Server-Start-Validation (DANACH)

**Verantwortlich:** Beide Teams

1. Alle laufenden `uvicorn` Prozesse beenden
2. Server neu starten mit:
   ```bash
   python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```
3. Health-Check:
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/api/auth/config
   ```

### Phase 3: OAuth-Functionality Test (FINAL)

**Verantwortlich:** OAuth-Team

1. Frontend Login-Page öffnen: `http://localhost:8000/login.html`
2. Google OAuth Flow testen
3. Session-Cookie Validation
4. Authenticated Endpoints testen

---

## 🔍 Modified Files Overview

### OAuth-Team Changes

| File | Changes | Status |
|------|---------|--------|
| `backend/main.py` | +24 lines (dotenv, auth routers) | ✅ MERGED |
| `requirements.txt` | +5 lines (dotenv, passlib, google-auth) | ✅ MERGED |
| `backend/auth/oauth.py` | NEW FILE | ✅ CREATED |
| `backend/auth/local.py` | NEW FILE | ✅ CREATED |
| `backend/auth/session.py` | NEW FILE | ✅ CREATED |
| `frontend/login.html` | NEW FILE | ✅ CREATED |

### Dependency-Team TODOs

| Package | Version | Installed? | Required By |
|---------|---------|------------|-------------|
| `python-dotenv` | >=1.0.0 | ✅ 1.2.2 | main.py |
| `passlib[bcrypt]` | >=1.7.4 | ✅ 1.7.4 | auth/local.py |
| `elasticsearch` | >=8.12.0 | ❌ MISSING | rag/es_store.py |
| `elasticsearch-dsl` | >=8.12.0 | ❌ MISSING | rag/es_store.py |

---

## ⚠️ Merge-Conflict Prevention

### Critical Files (koordinierte Änderungen erforderlich)

1. **requirements.txt**
   - OAuth-Team: +3 dependencies (dotenv, passlib, google-auth)
   - Status: ✅ Bereits committed
   - Konfliktpotential: NIEDRIG (neue Zeilen)

2. **backend/main.py**
   - OAuth-Team: +dotenv import, +auth routers
   - Status: ✅ Bereits geändert
   - Konfliktpotential: MITTEL (neue Imports, neue Router)

### Empfehlung

**VOR** weiteren Änderungen:
```bash
# Check uncommitted changes
git status

# Stash wenn nötig
git stash

# Install missing dependencies
pip install elasticsearch elasticsearch-dsl

# Test server start
python -m uvicorn backend.main:app --reload
```

---

## 🚀 Next Steps

### JETZT (Blocker beheben)

- [ ] **Dependency-Team:** Install `elasticsearch` + `elasticsearch-dsl`
- [ ] **Beide Teams:** Koordination über Git Status

### DANACH (Funktionalität testen)

- [ ] **OAuth-Team:** Server-Start validieren
- [ ] **OAuth-Team:** OAuth Flow testen
- [ ] **Beide Teams:** Integration Tests

### SPÄTER (Cleanup)

- [ ] Code Review der Auth-Implementierung
- [ ] Dokumentation in AUTH_README.md updaten
- [ ] Git Commit mit konsistenter Message

---

## 📞 Koordinations-Protokoll

**Regel:** Alle Änderungen an `requirements.txt` und `backend/main.py` müssen koordiniert werden!

**Kommunikation über:** `@architect` mention

**Konflikt-Resolution:**
1. Git Status prüfen
2. Bei Konflikten: Koordination mit Architekt
3. Gemeinsamer Merge-Plan

---

**Status-Update:** Warte auf Dependency-Installation durch paralleles Team
