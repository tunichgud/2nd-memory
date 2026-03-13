# Profile Management Feature

**Status**: ✅ Backend implemented
**Version**: 2.0.0
**Last Updated**: 2026-03-10

---

## Übersicht

Users können ihren eigenen Anzeigenamen (display_name) in ihrem Profil ändern.

### User Story

**Als User möchte ich** meinen Anzeigenamen ändern können,
**damit ich** meine Identität im System nach meinen Wünschen darstellen kann.

### Acceptance Criteria

✅ User kann display_name über API ändern
✅ Validierung: Mindestens 1 Zeichen, maximal 100 Zeichen
✅ Leere oder whitespace-only Namen werden abgelehnt
⏳ Frontend-UI fehlt noch (siehe unten)
⏳ Authentication: Aktuell kein Schutz, User kann jeden Namen ändern (wird mit Phase 2 behoben)

---

## Backend Implementation

### API Endpoint

**PATCH** `/api/v1/users/{user_id}`

**Request Body**:
```json
{
  "display_name": "Neuer Name"
}
```

**Response** (200 OK):
```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "display_name": "Neuer Name",
  "created_at": 1710072000,
  "is_active": true
}
```

**Error Responses**:
- `400 Bad Request`: Display name leer oder > 100 Zeichen
- `404 Not Found`: User existiert nicht

### Code Location

**File**: [`backend/api/v1/users.py:66-108`](backend/api/v1/users.py#L66-L108)

**Model**: [`backend/db/models.py:10-14`](backend/db/models.py#L10-L14) (User)

### Validierung

```python
# Nicht leer
if not req.display_name or len(req.display_name.strip()) == 0:
    raise HTTPException(status_code=400, detail="Display name darf nicht leer sein")

# Max. 100 Zeichen
if len(req.display_name) > 100:
    raise HTTPException(status_code=400, detail="Display name darf maximal 100 Zeichen lang sein")
```

### Security Hinweis (TODO)

⚠️ **Aktuell ungeschützt**: Jeder kann jeden User-Namen ändern.

**Sobald Authentication implementiert ist** (Phase 2), muss dieser Endpoint geschützt werden:

```python
@router.patch("/{user_id}", response_model=User)
async def update_user_profile(
    user_id: str,
    req: UpdateProfileRequest,
    current_user_id: str = Depends(get_current_user),  # ← JWT-Auth
    db: aiosqlite.Connection = Depends(get_db)
):
    # Nur eigenes Profil oder Admin
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # ... rest of implementation
```

**Siehe auch**: [Authentication Architecture (PRODUCT_ANALYSIS.md)](../PRODUCT_ANALYSIS.md) Phase 2

---

## Frontend Implementation (TODO)

### Einstellungen-Tab (Settings)

**Location**: [`frontend/index.html`](../frontend/index.html) Tab "Einstellungen"

**Wireframe**:

```
┌────────────────────────────────────────────┐
│ Einstellungen                              │
├────────────────────────────────────────────┤
│                                            │
│ Profil                                     │
│ ┌────────────────────────────────────────┐ │
│ │ Anzeigename                            │ │
│ │ ┌──────────────────────────────────┐   │ │
│ │ │ Manfred Mustermann              ✎│   │ │
│ │ └──────────────────────────────────┘   │ │
│ │                                        │ │
│ │ [ Speichern ]                          │ │
│ └────────────────────────────────────────┘ │
│                                            │
│ Datenschutz                                │
│ ┌────────────────────────────────────────┐ │
│ │ ☑ Gesichtserkennung erlauben           │ │
│ │ ☑ GPS-Daten speichern                  │ │
│ │ ☑ WhatsApp-Nachrichten verarbeiten     │ │
│ └────────────────────────────────────────┘ │
└────────────────────────────────────────────┘
```

### JavaScript Implementation (Vorschlag)

```javascript
// In frontend/index.html, Einstellungen-Tab
async function updateDisplayName() {
    const userId = localStorage.getItem('user_id') || '00000000-0000-0000-0000-000000000001';
    const newName = document.getElementById('display-name-input').value.trim();

    if (!newName || newName.length === 0) {
        alert('Name darf nicht leer sein');
        return;
    }

    if (newName.length > 100) {
        alert('Name darf maximal 100 Zeichen lang sein');
        return;
    }

    try {
        const response = await fetch(`/api/v1/users/${userId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: newName })
        });

        if (!response.ok) {
            const error = await response.json();
            alert(`Fehler: ${error.detail}`);
            return;
        }

        const updatedUser = await response.json();
        console.log('Profil aktualisiert:', updatedUser);

        // UI aktualisieren
        document.querySelector('.user-display-name').textContent = updatedUser.display_name;
        alert('Name erfolgreich geändert!');
    } catch (err) {
        console.error('Fehler beim Aktualisieren:', err);
        alert('Netzwerkfehler');
    }
}
```

### UX Improvements

**Inline-Bearbeitung** (empfohlen):
- Klick auf Stift-Icon → Input wird editierbar
- Auto-save nach 1 Sekunde Pause oder Enter-Taste
- Feedback: "Gespeichert ✓" für 2 Sekunden anzeigen

**Accessibility**:
- `<label for="display-name-input">Anzeigename</label>`
- `aria-label="Anzeigename bearbeiten"` auf Stift-Icon
- Keyboard navigation: Tab zu Input, Enter zum Speichern

**Mobile**:
- Input min. 44x44px Touch-Target
- Autofocus beim Öffnen
- Native Keyboard mit `type="text"` und `autocomplete="name"`

---

## Testing

### Manual Testing

```bash
# 1. User erstellen
curl -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Test User"}'

# Response: {"id": "abc-123", "display_name": "Test User", ...}

# 2. Namen ändern
curl -X PATCH http://localhost:8000/api/v1/users/abc-123 \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Neuer Name"}'

# Response: {"id": "abc-123", "display_name": "Neuer Name", ...}

# 3. Validierung testen (sollte 400 zurückgeben)
curl -X PATCH http://localhost:8000/api/v1/users/abc-123 \
  -H "Content-Type: application/json" \
  -d '{"display_name": ""}'

# 4. Nicht-existierender User (sollte 404 zurückgeben)
curl -X PATCH http://localhost:8000/api/v1/users/invalid-id \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Test"}'
```

### Unit Tests (TODO)

**File**: `tests/backend/api/v1/test_users.py` (neu erstellen)

```python
import pytest
from httpx import AsyncClient
from backend.main import app

@pytest.mark.asyncio
async def test_update_user_profile():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        response = await ac.post("/api/v1/users", json={"display_name": "Original"})
        user_id = response.json()["id"]

        # Update name
        response = await ac.patch(f"/api/v1/users/{user_id}", json={"display_name": "Updated"})
        assert response.status_code == 200
        assert response.json()["display_name"] == "Updated"

@pytest.mark.asyncio
async def test_update_user_profile_empty_name():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/users", json={"display_name": "Test"})
        user_id = response.json()["id"]

        # Empty name should fail
        response = await ac.patch(f"/api/v1/users/{user_id}", json={"display_name": ""})
        assert response.status_code == 400
        assert "leer" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_update_user_profile_too_long():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/users", json={"display_name": "Test"})
        user_id = response.json()["id"]

        # Name > 100 chars should fail
        long_name = "A" * 101
        response = await ac.patch(f"/api/v1/users/{user_id}", json={"display_name": long_name})
        assert response.status_code == 400
        assert "100" in response.json()["detail"]

@pytest.mark.asyncio
async def test_update_nonexistent_user():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.patch("/api/v1/users/invalid-id", json={"display_name": "Test"})
        assert response.status_code == 404
```

---

## Integration mit Authentication (Phase 2)

Wenn Authentication implementiert wird, muss Folgendes angepasst werden:

### 1. Security Middleware hinzufügen

```python
from backend.auth.security import get_current_user

@router.patch("/{user_id}", response_model=User)
async def update_user_profile(
    user_id: str,
    req: UpdateProfileRequest,
    current_user_id: str = Depends(get_current_user),  # ← NEU
    db: aiosqlite.Connection = Depends(get_db)
):
    # Nur eigenes Profil bearbeiten erlaubt
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Du kannst nur dein eigenes Profil bearbeiten")

    # ... rest bleibt gleich
```

### 2. Audit Logging

```python
from backend.auth.security import log_security_event

# Nach erfolgreichem Update:
await log_security_event(
    db=db,
    user_id=user_id,
    event_type="profile_update",
    success=True,
    metadata={"old_name": old_name, "new_name": req.display_name}
)
```

### 3. Frontend: JWT-Token mitschicken

```javascript
const token = localStorage.getItem('access_token');

const response = await fetch(`/api/v1/users/${userId}`, {
    method: 'PATCH',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`  // ← NEU
    },
    body: JSON.stringify({ display_name: newName })
});
```

---

## API Documentation (OpenAPI)

FastAPI generiert automatisch die Docs unter:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**Screenshot** (nach `/docs` Besuch):

![PATCH /api/v1/users/{user_id}](https://via.placeholder.com/800x400?text=OpenAPI+Docs+Screenshot)

---

## Change Log

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-03-10 | 2.0.0 | Initiale Implementierung (Backend) |
| TBD | 2.1.0 | Frontend-UI hinzufügen |
| TBD | 3.0.0 | Authentication + Authorization integrieren |

---

## Related Documents

- [Product Analysis](../PRODUCT_ANALYSIS.md) – Phase 2 Authentication Roadmap
- [UX Analysis](../UX_ANALYSIS.md) – Wireframes für Account Settings
- [Authentication Architecture](../AUTHENTICATION_ARCHITECTURE.md) – JWT Implementation
- [Backend API v1](../backend/api/v1/users.py) – Implementation

---

## Next Steps

**Für MVP Launch:**

1. ✅ Backend Endpoint implementiert
2. ⏳ Frontend UI erstellen (Einstellungen-Tab erweitern)
3. ⏳ Unit Tests schreiben
4. ⏳ E2E Test mit Playwright

**Für Phase 2 (Authentication):**

5. ⏳ `get_current_user` Dependency hinzufügen
6. ⏳ Authorization Check (user_id == current_user_id)
7. ⏳ Audit Logging für Profil-Änderungen
8. ⏳ Rate Limiting (max. 10 Updates pro Minute)

**Für Phase 3 (Advanced Features):**

9. ⏳ Profilbild-Upload
10. ⏳ Bio/Beschreibung hinzufügen
11. ⏳ Email-Änderung mit Verifikation
12. ⏳ Account-Löschung (DSGVO Art. 17)
