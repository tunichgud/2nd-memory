"""
consent.py – /api/v1/consent Endpunkte (DSGVO Art. 9)
"""
from __future__ import annotations

import time
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import aiosqlite

from backend.db.database import get_db
from backend.db.models import Consent, ConsentUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/consent", tags=["v1/consent"])


class ConsentStatus(BaseModel):
    biometric_photos: bool
    gps: bool
    messages: bool


def _anonymize_ip(request: Request) -> str:
    """Anonymisiert IP auf letztes Oktet (z.B. 192.168.1.x)."""
    ip = request.client.host if request.client else "unknown"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.x"
    return "x"


@router.get("/{user_id}", response_model=ConsentStatus)
async def get_consent(user_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Gibt den aktuellen Consent-Status eines Users zurück."""
    cursor = await db.execute(
        "SELECT scope, granted FROM consents WHERE user_id = ?", (user_id,)
    )
    rows = await cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="User oder Consents nicht gefunden")
    status = {r["scope"]: bool(r["granted"]) for r in rows}
    return ConsentStatus(
        biometric_photos=status.get("biometric_photos", False),
        gps=status.get("gps", False),
        messages=status.get("messages", False),
    )


@router.post("/{user_id}", response_model=ConsentStatus)
async def update_consent(
    user_id: str,
    update: ConsentUpdate,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Speichert den Consent-Status eines Users (Audit-Trail in DB)."""
    # User-Existenz prüfen
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    ip_hint = _anonymize_ip(request)
    now = int(time.time())

    scopes = {
        "biometric_photos": update.biometric_photos,
        "gps": update.gps,
        "messages": update.messages,
    }

    for scope, granted in scopes.items():
        await db.execute(
            """INSERT INTO consents (user_id, scope, granted, granted_at, ip_hint)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, scope) DO UPDATE SET
                 granted = excluded.granted,
                 granted_at = excluded.granted_at,
                 ip_hint = excluded.ip_hint""",
            (user_id, scope, int(granted), now, ip_hint),
        )

    await db.commit()
    logger.info("Consent aktualisiert für User %s: %s (IP: %s)", user_id, scopes, ip_hint)

    return ConsentStatus(
        biometric_photos=update.biometric_photos,
        gps=update.gps,
        messages=update.messages,
    )
