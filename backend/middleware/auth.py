"""
auth.py – Authentication Middleware für memosaur

Schützt API-Routen vor unauthentifizierten Zugriffen.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Cookie
import aiosqlite

from backend.db.database import get_db
from backend.auth.session import get_session_user_id, SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

# Feature-Flag: Authentication aktivieren/deaktivieren
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"


async def get_current_user_id(
    session_id: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    db: aiosqlite.Connection = Depends(get_db)
) -> str:
    """
    FastAPI-Dependency: Authentifizierung erforderlich.

    Gibt die User-ID des eingeloggten Users zurück.
    Wirft HTTPException 401, wenn nicht eingeloggt.

    Usage:
        @router.get("/protected")
        async def protected_route(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id}
    """
    # Feature-Flag: Auth deaktiviert
    if not AUTH_ENABLED:
        # Fallback auf Default-User für Development
        logger.debug("Auth deaktiviert - nutze Default-User")
        from backend.db.database import DEFAULT_USER_ID
        return DEFAULT_USER_ID

    # Keine Session-Cookie
    if not session_id:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Cookie"}
        )

    # Session validieren
    user_id = await get_session_user_id(db, session_id)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Cookie"}
        )

    return user_id


async def get_optional_user_id(
    session_id: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    db: aiosqlite.Connection = Depends(get_db)
) -> Optional[str]:
    """
    FastAPI-Dependency: Optionale Authentifizierung.

    Gibt User-ID zurück wenn eingeloggt, sonst None.
    Wirft KEINE Exception.

    Usage:
        @router.get("/public-or-protected")
        async def route(user_id: Optional[str] = Depends(get_optional_user_id)):
            if user_id:
                return {"message": "logged in", "user_id": user_id}
            return {"message": "not logged in"}
    """
    # Feature-Flag: Auth deaktiviert
    if not AUTH_ENABLED:
        from backend.db.database import DEFAULT_USER_ID
        return DEFAULT_USER_ID

    if not session_id:
        return None

    return await get_session_user_id(db, session_id)
