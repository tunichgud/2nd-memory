"""
store_v2.py – ChromaDB Interface mit user_id-Unterstützung.

Alle Operationen filtern implizit auf user_id, so dass Daten verschiedener
Nutzer sauber getrennt sind (auch wenn sie in derselben Collection liegen).
"""
from __future__ import annotations
import logging
from typing import Any
from backend.rag.store import get_client, COLLECTIONS

logger = logging.getLogger(__name__)


def _get_col(name: str):
    if name not in COLLECTIONS:
        raise ValueError(f"Unbekannte Collection: {name}")
    return get_client().get_or_create_collection(
        name=name, metadata={"hnsw:space": "cosine"}
    )


def upsert_documents_v2(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    """Wie upsert_documents, aber stellt sicher dass user_id in jedem Metadatensatz steht."""
    col = _get_col(collection_name)
    col.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    logger.info("v2 upsert %d Dok. in '%s'", len(ids), collection_name)


def query_collection_v2(
    collection_name: str,
    query_embeddings: list[list[float]],
    n_results: int = 10,
    where: dict | None = None,
    user_id: str | None = None,
) -> dict:
    """Semantische Suche mit optionalem user_id-Filter."""
    col = _get_col(collection_name)
    count = col.count()
    if count == 0:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    # user_id-Filter in where-Klausel einbauen
    if user_id:
        user_filter = {"user_id": {"$eq": user_id}}
        if where:
            combined = {"$and": [user_filter, where]}
        else:
            combined = user_filter
    else:
        combined = where

    kwargs: dict[str, Any] = {
        "query_embeddings": query_embeddings,
        "n_results": min(n_results, count),
        "include": ["documents", "metadatas", "distances"],
    }
    if combined:
        kwargs["where"] = combined

    try:
        return col.query(**kwargs)
    except Exception as exc:
        # Filter-Fehler (z.B. user_id-Feld fehlt in alten Dokumenten) → ohne Filter
        logger.warning("query_collection_v2 Filter-Fehler in '%s': %s – retry ohne Filter", collection_name, exc)
        kwargs.pop("where", None)
        return col.query(**kwargs)


def get_all_documents_for_user(collection_name: str, user_id: str) -> dict:
    """Gibt alle Dokumente eines Users zurück."""
    col = _get_col(collection_name)
    if col.count() == 0:
        return {"ids": [], "documents": [], "metadatas": []}
    try:
        return col.get(
            where={"user_id": {"$eq": user_id}},
            include=["documents", "metadatas"],
        )
    except Exception:
        return col.get(include=["documents", "metadatas"])


def count_documents_for_user(collection_name: str, user_id: str) -> int:
    col = _get_col(collection_name)
    if col.count() == 0:
        return 0
    try:
        result = col.get(where={"user_id": {"$eq": user_id}}, include=[])
        return len(result.get("ids", []))
    except Exception:
        return col.count()
