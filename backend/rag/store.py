"""
store.py – ChromaDB Interface für memosaur.

Verwaltet vier Collections:
  - photos       : Fotos mit GPS, Personen, KI-Beschreibung
  - reviews      : Google Maps Bewertungen
  - saved_places : Google Maps Gespeicherte Orte
  - messages     : WhatsApp / Signal Nachrichten (vorbereitet)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
import yaml

logger = logging.getLogger(__name__)

COLLECTIONS = ["photos", "reviews", "saved_places", "messages"]


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
