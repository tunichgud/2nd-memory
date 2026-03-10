"""
oauth.py – Google OAuth 2.0 Authentication

Implementiert den OAuth-Flow für Google Sign-In.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.db.database import get_db
from backend.auth.session import create_session, SESSION_COOKIE_NAME, SESSION_EXPIRY_SECONDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Google OAuth Konfiguration (aus ENV)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

# Frontend URL für Redirects
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")


@router.get("/config")
async def get_auth_config():
    """Gibt öffentliche Auth-Konfiguration zurück (für Frontend)."""
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
        "oauth_configured": bool(GOOGLE_CLIENT_ID),
        "passkey_enabled": False  # TODO: Passkey-Feature-Flag
    }


class GoogleTokenRequest(BaseModel):
    """Request-Body für Google OAuth Token-Exchange (frontend-initiiert)."""
    credential: str  # JWT-Token von Google


async def get_first_user(db: aiosqlite.Connection) -> Optional[dict]:
    """Holt den ersten (einzigen) User aus der DB."""
    cursor = await db.execute(
        "SELECT id, display_name, google_id, email, picture_url FROM users LIMIT 1"
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    return None


async def create_user_from_google(
    db: aiosqlite.Connection,
    google_id: str,
    email: str,
    display_name: str,
    picture_url: Optional[str] = None
) -> str:
    """
    Erstellt einen neuen User aus Google-Profildaten.

    Returns:
        user_id
    """
    import uuid
    import time

    user_id = str(uuid.uuid4())
    now = int(time.time())

    await db.execute(
        """INSERT INTO users (id, display_name, google_id, email, picture_url, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, display_name, google_id, email, picture_url, now)
    )
    await db.commit()

    logger.info("Neuer User erstellt: %s (Google ID: %s)", display_name, google_id)
    return user_id


async def update_user_from_google(
    db: aiosqlite.Connection,
    user_id: str,
    google_id: str,
    email: str,
    display_name: str,
    picture_url: Optional[str] = None
) -> None:
    """Aktualisiert User-Daten mit Google-Profil."""
    await db.execute(
        """UPDATE users
           SET google_id = ?, email = ?, display_name = ?, picture_url = ?
           WHERE id = ?""",
        (google_id, email, display_name, picture_url, user_id)
    )
    await db.commit()
    logger.info("User %s aktualisiert mit Google-Profil", user_id)


@router.post("/google/token")
async def google_token_auth(
    token_request: GoogleTokenRequest,
    request: Request,
    response: Response,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Authentifizierung mit Google OAuth Token (von Frontend).

    Flow:
    1. Frontend nutzt Google Sign-In Library
    2. Frontend erhält JWT-Credential von Google
    3. Frontend sendet Credential an diesen Endpoint
    4. Backend verifiziert Token mit Google
    5. Backend erstellt/findet User
    6. Backend erstellt Session-Cookie
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google OAuth not configured (missing GOOGLE_CLIENT_ID)")

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        # Verifiziere Google JWT
        idinfo = id_token.verify_oauth2_token(
            token_request.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )

        # Extrahiere User-Info
        google_user_id = idinfo["sub"]
        email = idinfo.get("email")
        display_name = idinfo.get("name", email)
        picture_url = idinfo.get("picture")

        logger.info("Google-Login: %s (%s)", display_name, email)

    except ValueError as e:
        logger.error("Google Token Verification failed: %s", e)
        raise HTTPException(401, "Invalid Google token")

    # SINGLE-USER-CONSTRAINT: Prüfe ob bereits ein User existiert
    existing_user = await get_first_user(db)

    if not existing_user:
        # Erster Login: User anlegen
        user_id = await create_user_from_google(
            db, google_user_id, email, display_name, picture_url
        )
    else:
        # System hat bereits einen User
        if existing_user.get("google_id") and existing_user["google_id"] != google_user_id:
            raise HTTPException(
                403,
                "Dieses System ist bereits mit einem anderen Google-Account registriert"
            )

        # Update Google-ID falls noch nicht gesetzt
        if not existing_user.get("google_id"):
            await update_user_from_google(
                db, existing_user["id"], google_user_id, email, display_name, picture_url
            )

        user_id = existing_user["id"]

    # Erstelle Session
    session_id = await create_session(db, user_id, request)

    # Setze Session-Cookie
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
            "display_name": display_name,
            "email": email,
            "picture_url": picture_url
        }
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session_id: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Logout: Löscht Session und Cookie."""
    if session_id:
        from backend.auth.session import delete_session
        await delete_session(db, session_id)

    # Lösche Cookie
    response.delete_cookie(SESSION_COOKIE_NAME)

    return {"success": True}


@router.get("/status")
async def auth_status(
    session_id: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Prüft ob User eingeloggt ist."""
    if not session_id:
        return {"authenticated": False}

    from backend.auth.session import get_session_user_id

    user_id = await get_session_user_id(db, session_id)
    if not user_id:
        return {"authenticated": False}

    # Hole User-Info
    cursor = await db.execute(
        "SELECT id, display_name, email, picture_url FROM users WHERE id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "user": dict(row)
    }
