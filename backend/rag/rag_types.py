"""
rag_types.py – Geteilte Typdefinitionen für das RAG-Subsystem.

Alle TypedDicts und Protokoll-Typen die über Modul-Grenzen hinweg genutzt
werden gehören hierher — keine Business-Logik.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable, TypedDict


# ---------------------------------------------------------------------------
# Daten-Typen
# ---------------------------------------------------------------------------

class Source(TypedDict):
    """Ein einzelnes Retrieval-Ergebnis aus einer ChromaDB-Collection."""
    id: str
    collection: str
    score: float
    document: str
    metadata: dict[str, Any]


class RetrievalParams(TypedDict, total=False):
    """
    Parameter für einen Retrieval-Call.

    Alle Felder optional (total=False), damit Partial-Updates beim
    Thinking-Mode-Drilling einfach per {**base, **focus} gemerged werden.
    """
    date_from: str | None
    date_to: str | None
    keywords: list[str]
    persons: list[str]
    locations: list[str]
    collections: list[str]
    hint: str
    """Freitext-Hinweis für den Retriever (wird geloggt, nicht für Filterung genutzt)."""


# ---------------------------------------------------------------------------
# Callable-Typen
# ---------------------------------------------------------------------------

# Eine Funktion die RetrievalParams entgegennimmt und einen komprimierten
# Kontext-String zurückgibt — wird vom Thinking Mode für aktives Nachforschen
# verwendet.
RetrievalFn = Callable[[RetrievalParams], Awaitable[str]]
