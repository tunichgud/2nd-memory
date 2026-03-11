"""
store.py – ChromaDB Interface für memosaur.

Verwaltet Collections:
  - photos         : Fotos mit GPS, Personen, KI-Beschreibung
  - reviews        : Google Maps Bewertungen
  - saved_places   : Google Maps Gespeicherte Orte
  - messages       : WhatsApp / Signal Nachrichten
  - faces          : Gesichtserkennungs-Embeddings
  - whatsapp_config: WhatsApp Bot Konfiguration
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
import yaml

logger = logging.getLogger(__name__)

COLLECTIONS = ["photos", "reviews", "saved_places", "messages", "faces", "whatsapp_config"]
SEARCHABLE_COLLECTIONS = ["photos", "reviews", "saved_places", "messages"]


def _get_data_dir() -> Path:
    cfg_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    base = Path(__file__).resolve().parents[2]
    return base / cfg["paths"]["data_dir"]


_client: chromadb.PersistentClient | None = None


def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        data_dir = _get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
        logger.info("ChromaDB initialisiert in %s", data_dir / "chroma")
    return _client


def get_collection(name: str) -> chromadb.Collection:
    """Gibt eine Collection zurück (wird angelegt falls nicht vorhanden)."""
    if name not in COLLECTIONS:
        raise ValueError(f"Unbekannte Collection: {name}. Erlaubt: {COLLECTIONS}")
    client = get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_documents(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    """Fügt Dokumente in eine Collection ein (oder aktualisiert sie)."""
    col = get_collection(collection_name)
    col.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    logger.info("Upsert %d Dokumente in Collection '%s'", len(ids), collection_name)


def query_collection(
    collection_name: str,
    query_embeddings: list[list[float]],
    n_results: int = 10,
    where: dict | None = None,
) -> dict:
    """Semantische Suche in einer Collection."""
    col = get_collection(collection_name)
    kwargs: dict[str, Any] = {
        "query_embeddings": query_embeddings,
        "n_results": min(n_results, col.count() or 1),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    return col.query(**kwargs)


def count_documents(collection_name: str) -> int:
    """Gibt die Anzahl der Dokumente in einer Collection zurück."""
    return get_collection(collection_name).count()


def get_all_documents(collection_name: str) -> dict:
    """Gibt alle Dokumente einer Collection zurück (für Kartenansicht)."""
    col = get_collection(collection_name)
    if col.count() == 0:
        return {"ids": [], "documents": [], "metadatas": []}
    return col.get(include=["documents", "metadatas"])


def reset_collection(collection_name: str) -> None:
    """Löscht alle Dokumente einer Collection (für Re-Ingestion)."""
    client = get_client()
    client.delete_collection(collection_name)
    logger.warning("Collection '%s' gelöscht.", collection_name)


def get_indexed_ids(collection_name: str) -> set[str]:
    """Gibt eine Menge aller bereits indexierten IDs zurück."""
    col = get_collection(collection_name)
    if col.count() == 0:
        return set()
    return set(col.get(include=[])["ids"])


def keyword_search(
    collection_name: str,
    keywords: list[str],
    n_results: int | None = None,
    where: dict | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Volltext-Keyword-Suche via ChromaDB where_document ($contains).

    Sucht Chunks die ALLE angegebenen Keywords enthalten (AND-Verknüpfung).
    Gibt eine Liste von Dicts mit 'id', 'document', 'metadata', 'score' zurück.
    score=0.85 für alle Treffer (kein Ranking — nur Filterung).

    Args:
        collection_name: Name der Collection (z.B. "messages").
        keywords: Liste von Strings, die im Dokument vorkommen müssen.
            Leere Liste [] bedeutet nur Datum-Filter, kein Keyword-Filter.
        n_results: Maximale Anzahl Ergebnisse. None = alle Treffer zurückgeben.
        where: Optionaler Metadata-Filter (ChromaDB where-Syntax).
        date_from: Optionales Startdatum YYYY-MM-DD (filtert via timestamp-Metadata).
        date_to: Optionales Enddatum YYYY-MM-DD.
    """
    import time as _time

    col = get_collection(collection_name)
    if col.count() == 0:
        return []

    # Build where_document filter (AND über alle keywords)
    # Leere keywords-Liste → kein where_document-Filter (nur Datum/where)
    where_doc: dict | None = None
    if len(keywords) == 1:
        where_doc = {"$contains": keywords[0]}
    elif len(keywords) > 1:
        where_doc = {"$and": [{"$contains": kw} for kw in keywords]}

    # Kombiniere optionalen user-where-Filter
    combined_where: dict | None = where or None

    # n_results=None → alle Treffer (col.count() als obere Schranke)
    effective_limit = min(n_results, col.count()) if n_results is not None else col.count()

    try:
        get_kwargs: dict[str, Any] = {
            "limit": effective_limit,
            "include": ["documents", "metadatas"],
        }
        if where_doc is not None:
            get_kwargs["where_document"] = where_doc
        if combined_where:
            get_kwargs["where"] = combined_where

        result = col.get(**get_kwargs)
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        ids = result.get("ids") or []

        # Datum-Filter: post-filter via Python-String-Vergleich auf ISO-Timestamps.
        # Hintergrund: ChromaDB $gte/$lte erwartet numerische Werte, kann
        # ISO-Strings nicht vergleichen. ISO-Format ist lexikografisch sortierbar
        # (YYYY-MM-DDTHH:MM:SS), daher funktioniert String-Vergleich korrekt.
        date_from_str = (date_from or "")[:10]  # "YYYY-MM-DD" oder ""
        date_to_str = (date_to or "")[:10]      # "YYYY-MM-DD" oder ""

        results = []
        for doc_id, doc, meta in zip(ids, docs, metas):
            ts = str(meta.get("timestamp", ""))[:10]  # "YYYY-MM-DD"
            if date_from_str and ts and ts < date_from_str:
                continue
            if date_to_str and ts and ts > date_to_str:
                continue
            results.append({
                "id": f"{collection_name}_{doc_id}",
                "collection": collection_name,
                "document": doc,
                "metadata": meta,
                "score": 0.85,  # Keyword-Match: fixer Score höher als typischer Similarity-Score
            })

        return results

    except Exception as exc:
        logger.warning("keyword_search Fehler: %s", exc)
        return []
