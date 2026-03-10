"""
local.py – Username/Password Authentication

Implementiert lokale Authentifizierung als Alternative zu OAuth.
Einfacher Login ohne Google OAuth erforderlich.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Optional

import aiosqlite
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, validator

from backend.db.database import get_db
from backend.auth.session import create_session, SESSION_COOKIE_NAME, SESSION_EXPIRY_SECONDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """Request-Body für Registrierung."""
    username: str
    password: str
    display_name: str

    @validator('username')
    def username_valid(cls, v):
        if len(v) < 3:
            raise ValueError('Username muss mindestens 3 Zeichen lang sein')
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username darf nur Buchstaben, Zahlen, _ und - enthalten')
        return v.lower()  # Normalisiere zu Kleinbuchstaben

    @validator('password')
    def password_strong(cls, v):
        if len(v) < 8:
            raise ValueError('Passwort muss mindestens 8 Zeichen lang sein')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Passwort muss mindestens einen Großbuchstaben enthalten')
        if not re.search(r'[a-z]', v):
            raise ValueError('Passwort muss mindestens einen Kleinbuchstaben enthalten')
        if not re.search(r'[0-9]', v):
            raise ValueError('Passwort muss mindestens eine Zahl enthalten')
        return v


class LoginRequest(BaseModel):
    """Request-Body für Login."""
    username: str
    password: str


def hash_password(password: str) -> str:
    """Hasht ein Passwort mit bcrypt."""
    # bcrypt requires bytes
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Return as string for database storage
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifiziert ein Passwort gegen einen Hash."""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


async def get_first_user(db: aiosqlite.Connection) -> Optional[dict]:
    """Holt den ersten (einzigen) User aus der DB."""
    cursor = await db.execute(
        "SELECT id, display_name, username, email FROM users LIMIT 1"
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    return None


async def get_user_by_username(db: aiosqlite.Connection, username: str) -> Optional[dict]:
    """Holt einen User anhand des Usernamens."""
    cursor = await db.execute(
        """SELECT id, display_name, username, email, password_hash
           FROM users
           WHERE username = ?""",
        (username.lower(),)
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    return None


async def create_user_local(
    db: aiosqlite.Connection,
    username: str,
    password_hash: str,
    display_name: str
) -> str:
    """
    Erstellt einen neuen User mit Username/Password.

    Returns:
        user_id
    """
    user_id = str(uuid.uuid4())
    now = int(time.time())

    await db.execute(
        """INSERT INTO users (id, display_name, username, password_hash, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, display_name, username.lower(), password_hash, now)
    )
    await db.commit()

    logger.info("Neuer User erstellt: %s (username: %s)", display_name, username)
    return user_id


@router.post("/register")
async def register(
    req: RegisterRequest,
    request: Request,
    response: Response,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Registrierung mit Username/Password.

    SINGLE-USER-CONSTRAINT: Nur ein User pro System.
    Falls bereits ein User ohne Username existiert, wird dieser mit Username/Password ergänzt.
    """
    # Prüfe ob bereits ein User existiert
    existing_user = await get_first_user(db)

    if existing_user:
        # Fall 1: User hat bereits einen Username → Registrierung nicht erlaubt
        if existing_user.get("username"):
            raise HTTPException(
                403,
                "Dieses System hat bereits einen User mit Username. memosaur ist ein Single-User-System."
            )

        # Fall 2: User existiert OHNE Username (z.B. nur OAuth oder Default-User)
        # → Erlaube das Hinzufügen von Username/Password
        logger.info("Ergänze bestehenden User mit Username/Password: %s", existing_user['display_name'])

        # Password hashen
        password_hash = hash_password(req.password)

        # User mit Username/Password ergänzen
        await db.execute(
            """UPDATE users
               SET username = ?, password_hash = ?, display_name = ?
               WHERE id = ?""",
            (req.username.lower(), password_hash, req.display_name, existing_user["id"])
        )
        await db.commit()

        user_id = existing_user["id"]
    else:
        # Fall 3: Kein User vorhanden → Neuen User anlegen
        # Prüfe ob Username bereits existiert (sollte nicht passieren, aber sicher ist sicher)
        user_by_username = await get_user_by_username(db, req.username)
        if user_by_username:
            raise HTTPException(409, "Username bereits vergeben")

        # Password hashen
        password_hash = hash_password(req.password)

        # User anlegen
        user_id = await create_user_local(db, req.username, password_hash, req.display_name)

    # Session erstellen
    session_id = await create_session(db, user_id, request)

    # Session-Cookie setzen
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_EXPIRY_SECONDS,
        httponly=True,
        secure=False,  # TODO: True in Production (HTTPS)
        samesite="lax"
    )

    return {
        "success": True,
        "user": {
            "id": user_id,
            "display_name": req.display_name,
            "username": req.username
        }
    }


@router.post("/login/local")
async def login_local(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Login mit Username/Password."""
    # User finden
    user = await get_user_by_username(db, req.username)
    if not user:
        # Sicherheit: Gleiche Fehlermeldung wie bei falschem Passwort (Timing-Attack-Schutz)
        raise HTTPException(401, "Ungültiger Username oder Passwort")

    # Password prüfen
    if not user.get("password_hash"):
        # User existiert, aber hat kein Passwort (z.B. nur OAuth)
        raise HTTPException(401, "Dieser Account nutzt Google OAuth")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Ungültiger Username oder Passwort")

    # Session erstellen
    session_id = await create_session(db, user["id"], request)

    # Session-Cookie setzen
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_EXPIRY_SECONDS,
        httponly=True,
        secure=False,  # TODO: True in Production (HTTPS)
        samesite="lax"
    )

    return {
        "success": True,
        "user": {
            "id": user["id"],
            "display_name": user["display_name"],
            "username": user["username"],
            "email": user.get("email")
        }
    }
