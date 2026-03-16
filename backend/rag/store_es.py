"""
store_es.py – Thin Adapter: gleiche Interface wie store_v2.py, intern via es_store.

Ziel: Phase-3-Migration kann store_v2-Aufrufe durch store_es-Aufrufe ersetzen,
ohne die Aufrufer-Signatur zu ändern. Alle Funktionen delegieren an es_store.py
und konvertieren das Rückgabe-Format auf das ChromaDB-kompatible Dict-Format,
das der Rest der Codebase erwartet.

Verfügbarkeit-Fallback: Wenn Elasticsearch nicht erreichbar ist (_es_available
ist False), geben alle read-only-Funktionen leere Strukturen zurück. Schreib-
Operationen loggen eine Warnung und tun nichts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.rag.es_store import (
    _es_available,
    count_documents_es,
    delete_document_es,
    get_all_documents_es,
    get_document_by_id_es,
    keyword_search_es,
    query_es,
    upsert_documents_es,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def upsert_documents_v2(
    collection_name: str,
    ids: List[str],
    documents: List[str],
    embeddings: List[List[float]],
    metadatas: List[Dict[str, Any]],
) -> None:
    """Wie store_v2.upsert_documents_v2 — delegiert an es_store.upsert_documents_es.

    Args:
        collection_name: Ziel-Collection.
        ids: Dokument-IDs (eindeutig, werden als Elasticsearch _id verwendet).
        documents: Klartext-Inhalte der Dokumente.
        embeddings: Vektor-Einbettungen (muss len(ids) Einträge haben).
        metadatas: Metadaten-Dicts; jeder Eintrag sollte user_id enthalten.
    """
    if _es_available is False:
        logger.warning(
            "upsert_documents_v2 (ES): Elasticsearch nicht verfügbar, Upsert übersprungen."
        )
        return
    upsert_documents_es(
        collection_name=collection_name,
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


# ---------------------------------------------------------------------------
# Read — Vektor-Suche
# ---------------------------------------------------------------------------


def query_collection_v2(
    collection_name: str,
    query_embeddings: List[List[float]],
    n_results: int = 10,
    where: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Semantische Vektorsuche — delegiert an es_store.query_es.

    Gibt ein ChromaDB-kompatibles Dict zurück:
    ``{"ids": [[...]], "documents": [[...]], "metadatas": [[...]], "distances": [[...]]}``.
    Scores werden als Pseudo-Distanz (1 - score) abgebildet.

    Args:
        collection_name: Ziel-Collection.
        query_embeddings: Liste von Query-Vektoren (ChromaDB-Konvention: äussere Liste).
        n_results: Maximale Treffer pro Query-Vektor.
        where: Wird aktuell ignoriert (ES nutzt native Filter via query_es).
            Dokumentiert für Interface-Kompatibilität.
        user_id: Pflicht wenn ES-Modus aktiv.

    Returns:
        ChromaDB-ähnliches Ergebnis-Dict. Leere Struktur wenn ES down oder
        user_id fehlt.
    """
    empty: Dict[str, Any] = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }
    if _es_available is False:
        return empty
    if not user_id:
        logger.warning("query_collection_v2 (ES): user_id fehlt, leeres Ergebnis.")
        return empty

    if where:
        logger.debug(
            "query_collection_v2 (ES): where-Filter '%s' wird ignoriert (ES nutzt native Filter).",
            where,
        )

    # Nutze erstes Query-Embedding (ChromaDB erlaubt mehrere, ES nur eines pro Request)
    query_vector = query_embeddings[0]

    hits = query_es(
        collection_name=collection_name,
        query_vector=query_vector,
        user_id=user_id,
        n_results=n_results,
    )

    ids = [h["id"] for h in hits]
    documents = [h["document"] for h in hits]
    metadatas = [h["metadata"] for h in hits]
    # Cosine-Score [0,1] → Pseudo-Distanz [0,1] (kleinere Distanz = ähnlicher)
    distances = [max(0.0, 1.0 - h["score"]) for h in hits]

    return {
        "ids": [ids],
        "documents": [documents],
        "metadatas": [metadatas],
        "distances": [distances],
    }


# ---------------------------------------------------------------------------
# Read — alle Dokumente / Zählen
# ---------------------------------------------------------------------------


def get_all_documents_for_user(
    collection_name: str,
    user_id: str,
) -> Dict[str, Any]:
    """Gibt alle Dokumente eines Users zurück — ChromaDB-kompatibles Dict-Format.

    Args:
        collection_name: Ziel-Collection.
        user_id: Dokumente werden auf diesen User gefiltert.

    Returns:
        ``{"ids": [...], "documents": [...], "metadatas": [...]}``
    """
    empty: Dict[str, Any] = {"ids": [], "documents": [], "metadatas": []}
    if _es_available is False:
        return empty

    hits = get_all_documents_es(collection_name=collection_name, user_id=user_id)
    return {
        "ids": [h["id"] for h in hits],
        "documents": [h["document"] for h in hits],
        "metadatas": [h["metadata"] for h in hits],
    }


def count_documents_for_user(collection_name: str, user_id: str) -> int:
    """Zählt Dokumente eines Users — delegiert an es_store.count_documents_es.

    Args:
        collection_name: Ziel-Collection.
        user_id: Filter auf diesen User.

    Returns:
        Anzahl Dokumente als int. 0 wenn ES down.
    """
    return count_documents_es(collection_name=collection_name, user_id=user_id)


# ---------------------------------------------------------------------------
# Read — einzelnes Dokument
# ---------------------------------------------------------------------------


def get_document_by_id(
    collection_name: str,
    doc_id: str,
) -> Optional[Dict[str, Any]]:
    """Gibt ein einzelnes Dokument anhand seiner ID zurück.

    Args:
        collection_name: Ziel-Collection.
        doc_id: Elasticsearch-Dokument-ID.

    Returns:
        Dict mit id, document, metadata oder None wenn nicht gefunden / ES down.
    """
    return get_document_by_id_es(collection_name=collection_name, doc_id=doc_id)


# ---------------------------------------------------------------------------
# Write — Löschen
# ---------------------------------------------------------------------------


def delete_document(collection_name: str, doc_id: str) -> bool:
    """Löscht ein einzelnes Dokument — delegiert an es_store.delete_document_es.

    Args:
        collection_name: Ziel-Collection.
        doc_id: Elasticsearch-Dokument-ID.

    Returns:
        True wenn erfolgreich gelöscht, False sonst.
    """
    return delete_document_es(collection_name=collection_name, doc_id=doc_id)


# ---------------------------------------------------------------------------
# Read — Keyword-Suche
# ---------------------------------------------------------------------------


def keyword_search_v2(
    collection_name: str,
    query: str,
    user_id: str,
    n_results: int = 10,
    person_names: Optional[List[str]] = None,
    location_names: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """BM25 Keyword-Suche — delegiert an es_store.keyword_search_es.

    Gibt die gleiche Struktur zurück wie store.keyword_search:
    Liste von Dicts mit id, document, metadata, score, collection.

    Args:
        collection_name: Ziel-Collection.
        query: Volltext-Suchstring.
        user_id: Pflicht-Filter.
        n_results: Maximale Anzahl Treffer.
        person_names: Optionale Personen-Filter.
        location_names: Optionale Orts-Filter.
        date_from: Optionales Startdatum (ISO "YYYY-MM-DD").
        date_to: Optionales Enddatum.

    Returns:
        Liste von Treffer-Dicts. Leere Liste wenn ES down.
    """
    if _es_available is False:
        return []

    return keyword_search_es(
        collection_name=collection_name,
        query=query,
        user_id=user_id,
        n_results=n_results,
        person_names=person_names,
        location_names=location_names,
        date_from=date_from,
        date_to=date_to,
    )
