"""
retrieval.py – Einheitliche Hybrid-Retrieval-Funktion für memosaur.

Single Responsibility: Diese Datei ist der einzige Ort der weiß,
  wie semantische Suche + Keyword-Suche kombiniert werden.

Aufrufer (retriever_v3_stream, thinking_mode) importieren nur `retrieve`
und `build_retrieval_fn` — keine Kenntnis über retrieve_v2 / keyword_search
Interna nötig.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.rag.constants import (
    DEFAULT_MIN_SCORE,
    DEFAULT_N_PER_COLLECTION,
    KEYWORD_BUDGET_TOKENS,
    KEYWORD_MAX_TOKENS_PER_CHUNK,
    TOP_N_FULL,
    DEFAULT_TOKEN_BUDGET,
)
from backend.rag.rag_types import RetrievalFn, RetrievalParams, Source

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    user_id: str,
    params: RetrievalParams,
    n_per_collection: int = DEFAULT_N_PER_COLLECTION,
    min_score: float = DEFAULT_MIN_SCORE,
) -> tuple[list[Source], list[Source]]:
    """
    Hybrid-Retrieval: semantisch + optional keyword-basiert.

    Returns:
        (semantic_sources, keyword_sources)
        Beide Listen sind dedupliziert (keine gemeinsamen IDs).
        Aufrufer entscheiden selbst wie sie beide kombinieren —
        üblicherweise compress_sources(semantic, keyword_sources=keyword).
    """
    from backend.rag.retriever_v2 import retrieve_v2
    from backend.rag.store import keyword_search

    date_from: str | None = params.get("date_from")
    date_to: str | None = params.get("date_to")
    persons: list[str] = params.get("persons") or []
    locations: list[str] = params.get("locations") or []
    collections: list[str] | None = params.get("collections") or None
    keywords: list[str] = params.get("keywords") or []

    if params.get("hint"):
        logger.info("retrieve() hint: %s", params["hint"])

    # --- Semantisches Retrieval ---
    semantic_sources: list[Source] = retrieve_v2(
        query=query,
        user_id=user_id,
        person_names=persons,
        location_names=locations,
        collections=collections,
        n_per_collection=n_per_collection,
        min_score=min_score,
        date_from=date_from,
        date_to=date_to,
    )  # type: ignore[assignment]

    # --- Re-Ranking: Cross-Encoder bewertet (query, chunk)-Paare neu ---
    # Keyword-Quellen werden NICHT re-ranked (chronologischer Block bleibt unverändert).
    from backend.rag.reranker import rerank
    semantic_sources = rerank(query, semantic_sources, top_n=10)

    # --- Keyword-Retrieval (optional, nur bei schluesselwoerter) ---
    keyword_sources: list[Source] = []
    if keywords:
        existing_ids = {s["id"] for s in semantic_sources}
        kw_results = keyword_search(
            collection_name="messages",
            keywords=keywords,
            date_from=date_from,
            date_to=date_to,
        )
        for r in kw_results:
            if r["id"] not in existing_ids:
                keyword_sources.append(r)  # type: ignore[arg-type]
                existing_ids.add(r["id"])

        if keyword_sources:
            logger.info(
                "retrieve() keyword=%s → %d zusätzliche Chunks (eigener Block)",
                keywords, len(keyword_sources),
            )

    return semantic_sources, keyword_sources


def build_retrieval_fn(
    query: str,
    user_id: str,
    base_params: RetrievalParams,
) -> RetrievalFn:
    """
    Erstellt eine RetrievalFn-Closure für den Thinking Mode.

    Der Thinking Mode ruft diese Funktion mit fokussierten Parametern auf
    (z.B. engeres Datum, spezifische Keywords) und erhält einen
    komprimierten Kontext-String zurück.

    Die Closure mergt base_params mit den focus-Params (focus gewinnt).
    """
    from backend.rag.context_manager import compress_sources, ContextBudget

    async def retrieval_fn(focus: RetrievalParams) -> str:
        merged: RetrievalParams = {**base_params, **focus}  # type: ignore[misc]
        logger.info("Thinking Mode Nachforschung: %s", _summarize_params(focus))

        semantic, keyword = retrieve(query, user_id, merged)

        if not semantic and not keyword:
            return "(Keine weiteren Quellen für diesen Fokus gefunden)"

        return compress_sources(
            semantic,
            budget=ContextBudget(max_tokens=DEFAULT_TOKEN_BUDGET),
            top_n_full=TOP_N_FULL,
            keyword_sources=keyword or None,
        )

    return retrieval_fn


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _summarize_params(params: RetrievalParams) -> str:
    """Kompakte Log-Darstellung der Retrieval-Parameter."""
    parts = []
    if params.get("date_from") or params.get("date_to"):
        parts.append(f"datum={params.get('date_from')}–{params.get('date_to')}")
    if params.get("keywords"):
        parts.append(f"keywords={params['keywords']}")
    if params.get("persons"):
        parts.append(f"personen={params['persons']}")
    if params.get("hint"):
        parts.append(f"hint='{params['hint'][:40]}'")
    return ", ".join(parts) if parts else "(keine Parameter)"
