"""
session.py – Session-Management für 2nd Memory Authentication

Verwaltet Cookie-basierte Sessions für eingeloggte User.
"""

from __future__ import annotations

import secrets
import time
import logging
from typing import Optional

import aiosqlite
from fastapi import Cookie, HTTPException, Request

logger = logging.getLogger(__name__)

# Session-Konfiguration
SESSION_COOKIE_NAME = "2nd_memory_session"
SESSION_EXPIRY_DAYS = 30
SESSION_EXPIRY_SECONDS = SESSION_EXPIRY_DAYS * 24 * 60 * 60


def _anonymize_ip(request: Request) -> str:
    """Anonymisiert IP auf letztes Oktet (z.B. 192.168.1.x)."""
    ip = request.client.host if request.client else "unknown"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.x"
    return "x"


async def create_session(
    db: aiosqlite.Connection,
    user_id: str,
    request: Request
) -> str:
    """
    Erstellt eine neue Session für einen User.

    Returns:
        session_id: Die generierte Session-ID (für Cookie)
    """
    session_id = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + SESSION_EXPIRY_SECONDS

    user_agent = request.headers.get("user-agent", "unknown")[:200]  # Limit length
    ip_hint = _anonymize_ip(request)

    await db.execute(
        """INSERT INTO sessions (id, user_id, created_at, expires_at, user_agent, ip_hint)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, now, expires_at, user_agent, ip_hint)
    )
    await db.commit()

    logger.info("Session erstellt für User %s (expires in %d days)", user_id, SESSION_EXPIRY_DAYS)
    return session_id


async def get_session_user_id(
    db: aiosqlite.Connection,
    session_id: Optional[str]
) -> Optional[str]:
    """
    Validiert eine Session und gibt die User-ID zurück.

    Returns:
        user_id oder None (wenn Session ungültig/abgelaufen)
    """
    if not session_id:
        return None

    cursor = await db.execute(
        """SELECT user_id, expires_at FROM sessions WHERE id = ?""",
        (session_id,)
    )
    row = await cursor.fetchone()

    if not row:
        return None

    user_id, expires_at = row["user_id"], row["expires_at"]

    # Prüfe Expiry
    if expires_at < int(time.time()):
        logger.debug("Session %s abgelaufen", session_id[:10])
        # Cleanup: Lösche abgelaufene Session
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        return None

    return user_id


async def delete_session(
    db: aiosqlite.Connection,
    session_id: str
) -> None:
    """Löscht eine Session (Logout)."""
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.commit()
    logger.info("Session gelöscht: %s", session_id[:10])


async def cleanup_expired_sessions(db: aiosqlite.Connection) -> int:
    """
    Cleanup-Job: Löscht alle abgelaufenen Sessions.

    Returns:
        Anzahl gelöschter Sessions
    """
    cursor = await db.execute(
        "DELETE FROM sessions WHERE expires_at < ?",
        (int(time.time()),)
    )
    await db.commit()
    count = cursor.rowcount
    if count > 0:
        logger.info("Cleanup: %d abgelaufene Sessions gelöscht", count)
    return count
