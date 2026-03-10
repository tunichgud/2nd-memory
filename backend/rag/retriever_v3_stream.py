"""
retriever_v3_stream.py – Real-Time Streaming RAG mit Live-Denkprozess.

Neu gegenüber retriever_v3.py:
  - Streamt Events während der Arbeit (SSE)
  - User sieht Query-Analyse, Retrieval-Progress, Thoughts in Real-Time
  - Answer wird Chunk-by-Chunk gestreamt

Event-Typen:
  - query_analysis: Zeigt erkannte Personen/Datum/Collections
  - retrieval: Progress-Updates während Multi-Shot Retrieval
  - thought: Interne Reasoning-Schritte (optional, collapsible)
  - text: Streaming Answer (Char-by-Char)
  - sources: Finale Quellen-Liste
  - error: Fehlermeldungen
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import AsyncGenerator

from backend.rag.query_analyzer import analyze_query, AnalyzedQuery
from backend.rag.query_parser import parse_query, ParsedQuery  # LLM-basiertes Temporal Parsing!
from backend.rag.retriever_v3 import (
    retrieve_v3,
    expand_query_with_synonyms,
    _get_system_prompt_v3,
    _generate_no_results_message,
    _has_strict_date_filter,
)
from backend.rag.context_manager import compress_sources, ContextBudget
from backend.llm.connector import chat_stream

logger = logging.getLogger(__name__)


async def answer_v3_stream(
    query: str,
    user_id: str,
    chat_history: list[dict] | None = None,
    person_names: list[str] | None = None,
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = 0.2,
    date_from: str | None = None,
    date_to: str | None = None,
    use_chain_of_thought: bool = True,
    show_thoughts: bool = True,
) -> AsyncGenerator[str, None]:
    """
    RAG v3 mit Real-Time Streaming.

    Yields JSON-Strings für Server-Sent Events (SSE):
      {"type": "query_analysis", "content": {...}}
      {"type": "retrieval", "content": {...}}
      {"type": "thought", "content": "..."}
      {"type": "text", "content": "..."}
      {"type": "sources", "content": [...]}
      {"type": "error", "content": "..."}

    Args:
        query: User-Query
        user_id: User-ID
        chat_history: Optional Chat-Historie für Context
        person_names: Optional Personen-Filter
        location_names: Optional Orts-Filter
        collections: Zu durchsuchende Collections
        n_per_collection: Max Ergebnisse pro Collection
        min_score: Minimum Similarity Score
        date_from: Datum-Filter (von)
        date_to: Datum-Filter (bis)
        use_chain_of_thought: Chain-of-Thought für komplexe Queries?
        show_thoughts: Interne Thoughts zeigen? (für Debugging)

    Yields:
        JSON Strings für SSE Stream
    """
    try:
        # ====================================================================
        # Phase 1: Query Parsing (LLM-basiertes Temporal Reasoning!)
        # ====================================================================
        # Use query_parser for temporal extraction WITH chat_history context!
        parsed: ParsedQuery = parse_query(query, chat_history=chat_history)

        # Also run query_analyzer for Chain-of-Thought decomposition
        analyzed: AnalyzedQuery = analyze_query(query)

        # Stream Analysis Result (combine both results)
        yield _event("query_analysis", {
            "query": query,
            "persons": parsed.persons or analyzed.entities or [],
            "locations": parsed.locations or [],
            "date_from": parsed.date_from,
            "date_to": parsed.date_to,
            "query_type": analyzed.query_type,
            "complexity": analyzed.complexity,
            "relevant_collections": parsed.relevant_collections or analyzed.sub_queries[:3] if analyzed.sub_queries else []
        }) + "\n\n"

        # ====================================================================
        # Phase 2: Synonym Expansion (optional Thought)
        # ====================================================================
        query_variants = [query]
        if analyzed.complexity != "simple" and show_thoughts:
            yield _event("thought", "Erweitere Suche mit Synonymen für bessere Ergebnisse") + "\n\n"
            query_variants = expand_query_with_synonyms(query, max_variants=3)
            if len(query_variants) > 1:
                yield _event("thought", f"Nutze {len(query_variants)} Query-Varianten") + "\n\n"

        # ====================================================================
        # Phase 3: Multi-Shot Retrieval mit Progress
        # ====================================================================
        # WICHTIG: Yield BEFORE blocking calls für real-time streaming!

        if show_thoughts:
            yield _event("thought", f"Starte Suche in {len(collections or ['photos', 'messages', 'reviews'])} Collections") + "\n\n"

        # Yield "in progress" event BEFORE blocking retrieval
        # This ensures user sees progress immediately
        yield _event("retrieval", {
            "status": "in_progress",
            "message": "Durchsuche Datenbanken..."
        }) + "\n\n"

        # Force flush to client (critical for real-time UX!)
        import asyncio
        await asyncio.sleep(0)  # Yield control back to event loop

        # Override date filters with LLM-parsed values (better than regex!)
        effective_date_from = date_from or parsed.date_from
        effective_date_to = date_to or parsed.date_to

        # Log what we're using
        if effective_date_from or effective_date_to:
            logger.info(
                "Using LLM-parsed temporal filter: %s to %s",
                effective_date_from, effective_date_to
            )

        # Retrieval (synchron, blockiert ~1-2s)
        # TODO: Refactor zu async generator für collection-by-collection Progress
        # NOTE: retrieve_v3 doesn't accept date_from/date_to yet,
        # so we need to use retriever_v2 OR refactor retrieve_v3
        # WORKAROUND: Use ChromaDB query directly with metadata filters
        from backend.rag.retriever_v2 import retrieve_v2  # Has date_from/date_to support!

        sources = retrieve_v2(
            query=query,
            user_id=user_id,
            person_names=person_names or parsed.persons,
            location_names=location_names or parsed.locations,
            collections=collections or parsed.relevant_collections,
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=effective_date_from,
            date_to=effective_date_to,
        )

        # Stream Retrieval Results (AFTER retrieval completes)
        yield _event("retrieval", {
            "status": "completed",
            "total_sources": len(sources),
            "collections": list(set(s["collection"] for s in sources)) if sources else [],
            "top_score": round(sources[0]["score"], 2) if sources else 0.0
        }) + "\n\n"

        # ====================================================================
        # Phase 4: Handle Empty Results
        # ====================================================================
        if not sources and _has_strict_date_filter(analyzed):
            no_results_msg = _generate_no_results_message(query, analyzed)
            yield _event("text", no_results_msg) + "\n\n"
            yield _event("sources", []) + "\n\n"
            return

        # ====================================================================
        # Phase 5: Context Compression
        # ====================================================================
        if show_thoughts and len(sources) > 10:
            yield _event("thought", f"Komprimiere {len(sources)} Quellen für optimale Token-Nutzung") + "\n\n"

        context = compress_sources(sources, budget=ContextBudget(max_tokens=8000), top_n_full=5)

        # ====================================================================
        # Phase 6: Build Conversation Messages
        # ====================================================================
        messages = []

        # System Prompt
        messages.append({
            "role": "system",
            "content": _get_system_prompt_v3()
        })

        # Chat History (optional)
        if chat_history:
            # Limit to last 10 messages to avoid token overflow
            for msg in chat_history[-10:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # User Query + Context
        messages.append({
            "role": "user",
            "content": f"ANFRAGE: {query}\n\nKONTEXT:\n{context}"
        })

        # ====================================================================
        # Phase 7: Stream LLM Answer
        # ====================================================================
        if show_thoughts:
            yield _event("thought", "Generiere Antwort basierend auf gefundenen Quellen") + "\n\n"

        # Stream Answer via LLM
        async for event in chat_stream(messages):
            # chat_stream yields {"type": "text"|"thought"|"tool_call", "content": ...}
            # We pass it through as-is
            if event["type"] == "text":
                yield _event("text", event["content"]) + "\n\n"
            elif event["type"] in ("thought", "tool_call", "tool_result"):
                # Forward tool events to frontend
                yield _event(event["type"], event["content"]) + "\n\n"

        # ====================================================================
        # Phase 8: Send Sources (Final)
        # ====================================================================
        # Format sources for frontend
        formatted_sources = [
            {
                "id": s["id"],
                "collection": s["collection"],
                "score": round(s["score"], 2),
                "document": s["document"][:500],  # Truncate for transport
                "metadata": s["metadata"]
            }
            for s in sources[:20]  # Max 20 sources
        ]

        yield _event("sources", formatted_sources) + "\n\n"

    except Exception as exc:
        logger.exception("Error in answer_v3_stream")
        yield _event("error", str(exc)) + "\n\n"


def _event(event_type: str, content: any) -> str:
    """
    Formatiert ein Event für SSE Streaming.

    Args:
        event_type: Event-Typ (query_analysis, retrieval, thought, text, sources, error)
        content: Event-Payload (String oder Dict)

    Returns:
        JSON String für SSE (ohne trailing \\n\\n)
    """
    return json.dumps({
        "type": event_type,
        "content": content
    }, ensure_ascii=False)


# ============================================================================
# TODO: Refactor retrieve_v3 zu async Generator für echten Progress
# ============================================================================

async def retrieve_v3_stream(
    query: str,
    user_id: str,
    analyzed: AnalyzedQuery,
    collections: list[str],
    n_per_collection: int = 6,
) -> AsyncGenerator[dict, None]:
    """
    Streaming-Version von retrieve_v3.

    Yields Progress Events während des Retrievals.

    TODO: Implementierung (aktuell Placeholder)
    """
    for i, col in enumerate(collections):
        # Stream Progress
        yield {
            "type": "retrieval_progress",
            "content": {
                "collection": col,
                "progress": f"{i+1}/{len(collections)}",
                "status": "searching"
            }
        }

        # TODO: Actual retrieval logic hier
        # results = await async_query_collection(col, ...)

        yield {
            "type": "retrieval_progress",
            "content": {
                "collection": col,
                "progress": f"{i+1}/{len(collections)}",
                "status": "completed",
                "results_count": 0  # TODO: Real count
            }
        }
