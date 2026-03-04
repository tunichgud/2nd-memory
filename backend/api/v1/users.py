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
    # Default-Consents anlegen
    for scope in ("biometric_photos", "gps", "messages"):
        await db.execute(
            "INSERT INTO consents (user_id, scope, granted, granted_at) VALUES (?, ?, 0, ?)",
            (user_id, scope, now),
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
