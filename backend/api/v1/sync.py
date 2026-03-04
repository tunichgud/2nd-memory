"""
sync.py – /api/v1/sync Endpunkte (Multi-Device Wörterbuch-Sync)

Der Server speichert nur den verschlüsselten AES-GCM Blob.
Das Passwort verlässt niemals den Browser.
"""
from __future__ import annotations

import base64
import time
import logging

from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

from backend.db.database import get_db
from backend.db.models import SyncBlobUpload, SyncBlobResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sync", tags=["v1/sync"])


@router.post("/{user_id}", status_code=201)
async def upload_blob(
    user_id: str,
    payload: SyncBlobUpload,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Lädt einen verschlüsselten Sync-Blob hoch und erhöht die Versionsnummer."""
    # User prüfen
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    # Aktuelle Version ermitteln
    cursor = await db.execute(
        "SELECT COALESCE(MAX(version), 0) as max_v FROM sync_blobs WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    next_version = (row["max_v"] or 0) + 1

    # Blob dekodieren + speichern
    try:
        blob_bytes = base64.b64decode(payload.blob)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges Base64 im blob-Feld")

    now = int(time.time())
    await db.execute(
        """INSERT INTO sync_blobs (user_id, device_hint, blob, iv, created_at, version)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, payload.device_hint, blob_bytes, payload.iv, now, next_version),
    )
    await db.commit()
    logger.info("Sync-Blob v%d gespeichert für User %s", next_version, user_id)
    return {"version": next_version, "created_at": now}


@router.get("/{user_id}", response_model=SyncBlobResponse)
async def download_blob(user_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Gibt den neuesten Sync-Blob zurück."""
    cursor = await db.execute(
        """SELECT blob, iv, version, created_at FROM sync_blobs
           WHERE user_id = ? ORDER BY version DESC LIMIT 1""",
        (user_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Kein Sync-Blob vorhanden")

    return SyncBlobResponse(
        blob=base64.b64encode(row["blob"]).decode(),
        iv=row["iv"],
        version=row["version"],
        created_at=row["created_at"],
    )


@router.get("/{user_id}/history")
async def blob_history(user_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Gibt alle Versionen eines Users zurück (für Rollback)."""
    cursor = await db.execute(
        """SELECT id, version, device_hint, created_at FROM sync_blobs
           WHERE user_id = ? ORDER BY version DESC""",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
