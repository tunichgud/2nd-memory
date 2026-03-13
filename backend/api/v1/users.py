"""
users.py – /api/v1/users Endpunkte
"""
from __future__ import annotations

import time
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite

from backend.db.database import get_db
from backend.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/users", tags=["v1/users"])


class CreateUserRequest(BaseModel):
    display_name: str


class UpdateProfileRequest(BaseModel):
    display_name: str


@router.get("", response_model=list[User])
async def list_users(db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT id, display_name, created_at, is_active FROM users ORDER BY created_at")
    rows = await cursor.fetchall()
    return [User(**dict(r)) for r in rows]


@router.post("", response_model=User, status_code=201)
async def create_user(req: CreateUserRequest, db: aiosqlite.Connection = Depends(get_db)):
    user_id = str(uuid.uuid4())
    now = int(time.time())
    await db.execute(
        "INSERT INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
        (user_id, req.display_name, now),
    )
    await db.commit()
    logger.info("Neuer User erstellt: %s (%s)", req.display_name, user_id)
    return User(id=user_id, display_name=req.display_name, created_at=now)


@router.get("/{user_id}", response_model=User)
async def get_user(user_id: str, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute(
        "SELECT id, display_name, created_at, is_active FROM users WHERE id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User nicht gefunden")
    return User(**dict(row))


@router.patch("/{user_id}", response_model=User)
async def update_user_profile(
    user_id: str,
    req: UpdateProfileRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Aktualisiert das Profil eines Users (z.B. display_name).

    HINWEIS: Sobald Authentication implementiert ist, sollte dieser Endpoint
    nur für den aktuell eingeloggten User oder Admins erlaubt sein.
    Beispiel: current_user_id: str = Depends(get_current_user)
              if current_user_id != user_id: raise HTTPException(403)
    """
    # Validierung: Display name nicht leer und max. 100 Zeichen
    if not req.display_name or len(req.display_name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Display name darf nicht leer sein")
    if len(req.display_name) > 100:
        raise HTTPException(status_code=400, detail="Display name darf maximal 100 Zeichen lang sein")

    # Prüfen ob User existiert
    cursor = await db.execute(
        "SELECT id, display_name, created_at, is_active FROM users WHERE id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    # Update ausführen
    await db.execute(
        "UPDATE users SET display_name = ? WHERE id = ?",
        (req.display_name.strip(), user_id)
    )
    await db.commit()

    logger.info("User-Profil aktualisiert: %s → %s", user_id, req.display_name)

    # Aktualisierten User zurückgeben
    cursor = await db.execute(
        "SELECT id, display_name, created_at, is_active FROM users WHERE id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    return User(**dict(row))
