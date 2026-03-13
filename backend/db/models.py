"""
models.py – Pydantic-Modelle für die SQLite-Entitäten.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class User(BaseModel):
    id: str
    display_name: str
    created_at: int
    is_active: bool = True


class SyncBlob(BaseModel):
    id: int | None = None
    user_id: str
    device_hint: str | None = None
    blob: bytes
    iv: str              # Base64-kodierter AES-GCM IV
    created_at: int
    version: int = 1


class SyncBlobUpload(BaseModel):
    blob: str            # Base64-kodierter verschlüsselter Blob
    iv: str              # Base64-kodierter IV
    device_hint: str | None = None


class SyncBlobResponse(BaseModel):
    blob: str            # Base64
    iv: str
    version: int
    created_at: int
