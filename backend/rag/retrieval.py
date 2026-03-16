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
    from backend.rag.store_es import keyword_search_v2 as keyword_search

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

    # --- Live-Echo-Filter: WhatsApp-Live-Nachrichten entfernen ---
    # Live-Echo-Messages sind Reflexionen der eigenen Queries an das System —
    # keine echten Erinnerungen, kontaminieren aber das Retrieval als False Positives.
    n_before = len(semantic_sources)
    semantic_sources = [s for s in semantic_sources if not s.get("id", "").startswith("wa_live_")]
    if len(semantic_sources) < n_before:
        logger.info(
            "Live-Echo-Filter: %d wa_live_* Chunk(s) entfernt",
            n_before - len(semantic_sources),
        )

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
            query=" ".join(keywords),
            user_id=user_id,
            n_results=20,
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
    initial_source_ids: set[str] | None = None,
) -> tuple[RetrievalFn, list[Source]]:
    """
    Erstellt eine RetrievalFn-Closure für den Thinking Mode.

    Der Thinking Mode ruft diese Funktion mit fokussierten Parametern auf
    (z.B. engeres Datum, spezifische Keywords) und erhält einen
    komprimierten Kontext-String zurück.

    Die Closure mergt base_params mit den focus-Params (focus gewinnt).

    Chunk-ID-Deduplication: Bereits dem Researcher gezeigte Chunks werden
    aus nachfolgenden Retrievals herausgefiltert. Wenn keine neuen Chunks
    vorhanden sind, gibt die Funktion einen leeren String zurück — das
    ist das Signal für thinking_mode_stream, den Loop zu beenden.

    Returns:
        (retrieval_fn, thinking_sources)
        thinking_sources ist ein geteiltes Mutable-List, das nach jedem
        Thinking-Mode-Re-Retrieval mit den abgerufenen Quellen befüllt wird.
        Reihenfolge entspricht der compress_sources-Sortierung ([1], [2], ...).
        Damit können Aufrufer die Sources nach dem Thinking Mode für das
        Frontend nutzen — [[n]]-Referenzen in der Antwort stimmen dann überein.
    """
    from backend.rag.context_manager import compress_sources, ContextBudget

    # Chunk-ID-Tracking: bereits gezeigte Chunks nicht erneut zeigen.
    # Mit initialen Sources vorbelegen, damit Iter-1-Retrieval keine Duplikate liefert.
    seen_ids: set[str] = set(initial_source_ids or [])
    thinking_sources: list[Source] = []

    async def retrieval_fn(focus: RetrievalParams) -> str:
        merged: RetrievalParams = {**base_params, **focus}  # type: ignore[misc]
        logger.info("Thinking Mode Nachforschung: %s", _summarize_params(focus))

        semantic, keyword = retrieve(query, user_id, merged)

        # Sortiere semantic sources so wie compress_sources es tut —
        # damit [[1]] im LLM-Output zu thinking_sources[0] passt.
        sort_order = focus.get("sort_order", "relevance")
        if sort_order == "date_desc":
            def _dk(s: Source) -> str:
                m = s.get("metadata", {})
                return m.get("date_iso") or m.get("timestamp") or ""
            sorted_sem = sorted(semantic, key=_dk, reverse=True)
        elif sort_order == "date_asc":
            def _dk(s: Source) -> str:  # type: ignore[misc]
                m = s.get("metadata", {})
                return m.get("date_iso") or m.get("timestamp") or ""
            sorted_sem = sorted(semantic, key=_dk)
        else:
            sorted_sem = sorted(semantic, key=lambda s: s.get("score", 0), reverse=True)

        # --- Chunk-ID-Deduplication: bereits gesehene IDs rausfiltern ---
        new_sem = [s for s in sorted_sem if s.get("id") not in seen_ids]
        new_kw  = [s for s in keyword    if s.get("id") not in seen_ids]

        if not new_sem and not new_kw:
            logger.info(
                "Thinking Mode: alle %d Chunks bereits gesehen — Early-Exit-Signal",
                len(sorted_sem) + len(keyword),
            )
            return ""  # Leerer String = Signal für Early Exit in thinking_mode_stream

        seen_ids.update(s.get("id") for s in new_sem + new_kw)
        logger.info(
            "Thinking Mode: %d neue Chunks (%d sem, %d kw), %d bereits gesehen",
            len(new_sem) + len(new_kw), len(new_sem), len(new_kw), len(seen_ids),
        )

        # Tracking: keyword sources nach semantic anhängen (eigener Block)
        thinking_sources.clear()
        thinking_sources.extend(new_sem + new_kw)

        return compress_sources(
            new_sem,
            budget=ContextBudget(max_tokens=DEFAULT_TOKEN_BUDGET),
            top_n_full=TOP_N_FULL,
            keyword_sources=new_kw or None,
            sort_order=sort_order,
        )

    return retrieval_fn, thinking_sources


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
