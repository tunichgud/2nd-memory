"""
models.py – Pydantic-Modelle für die SQLite-Entitäten.
"""

from __future__ import annotations

from pydantic import BaseModel


class User(BaseModel):
    id: str
    display_name: str
    created_at: int
    is_active: bool = True
