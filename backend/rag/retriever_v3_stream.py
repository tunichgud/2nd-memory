"""
retriever_v3_stream.py – Real-Time Streaming RAG mit Live-Denkprozess.

Architektur:
    answer_v3_stream() orchestriert klar benannte Phasen-Funktionen.
    Jede Phase hat eine einzige Aufgabe (SRP).

    Phase 1: _phase_parse()           — Query-Parsing (LLM + Analyzer)
    Phase 2: _phase_retrieve()        — Hybrid-Retrieval (semantisch + keyword)
    Phase 3: _phase_compress()        — Context Compression
    Phase 4: _phase_build_messages()  — LLM-Prompt zusammenstellen
    Phase 5: _phase_generate()        — LLM streamen (Standard oder Thinking Mode)

Thinking Mode ist Standard (use_thinking_mode=True per Default).

SSE-Event-Typen:
    query_id        — Query-ID sofort nach Start (für QS-Workflow)
    query_analysis  — Erkannte Personen/Datum/Collections
    retrieval       — Retrieval-Status (in_progress / completed)
    thought         — Interne Reasoning-Schritte
    researcher      — Thinking Mode: Researcher-Draft
    challenger      — Thinking Mode: Challenger-Einwände
    decider         — Thinking Mode: Decider-Entscheidung
    retrieval_focus — Thinking Mode: Aktiver Nachforschungs-Fokus
    thinking_start  — Thinking Mode: Start-Event
    thinking_end    — Thinking Mode: End-Event
    text            — Streaming Answer (Wort-für-Wort)
    sources         — Finale Quellen-Liste
    error           — Fehlermeldungen
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Any, Callable

from backend.llm.connector import chat_stream, get_cfg
from backend.rag.constants import (
    DEFAULT_MIN_SCORE,
    DEFAULT_N_PER_COLLECTION,
    DEFAULT_TOKEN_BUDGET,
    MAX_CHAT_HISTORY,
    MAX_SOURCES_DISPLAY,
    MAX_THINKING_ITERATIONS,
    TOP_N_FULL,
)
from backend.rag.context_manager import compress_sources, ContextBudget
from backend.rag.query_analyzer import analyze_query
from backend.rag.query_logger import start_trace
from backend.rag.query_parser import parse_query, ParsedQuery
from backend.rag.rag_types import RetrievalFn, RetrievalParams, Source
from backend.rag.retrieval import build_retrieval_fn, retrieve
from backend.rag.retriever_v3 import (
    _generate_no_results_message,
    _get_system_prompt_v3,
    _has_strict_date_filter,
)
from backend.rag.thinking_mode import thinking_mode_stream

logger = logging.getLogger(__name__)


# ============================================================================
# ÖFFENTLICHE API
# ============================================================================

async def answer_v3_stream(
    query: str,
    user_id: str,
    chat_history: list[dict] | None = None,
    person_names: list[str] | None = None,
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = DEFAULT_N_PER_COLLECTION,
    min_score: float = DEFAULT_MIN_SCORE,
    date_from: str | None = None,
    date_to: str | None = None,
    use_chain_of_thought: bool = True,
    show_thoughts: bool = True,
    use_thinking_mode: bool = True,
    thinking_max_iterations: int = MAX_THINKING_ITERATIONS,
) -> AsyncGenerator[str, None]:
    """
    RAG v3 mit Real-Time Streaming.

    Thinking Mode ist Standard (use_thinking_mode=True).
    Yields JSON-Strings für Server-Sent Events (SSE).
    """
    trace = start_trace(query)
    llm_answer_parts: list[str] = []

    yield _sse("query_id", trace.query_id)

    try:
        # ── Phase 1: Parsing ─────────────────────────────────────────────────
        parsed, analyzed, effective_date_from, effective_date_to = await _phase_parse(
            query=query,
            chat_history=chat_history,
            date_from=date_from,
            date_to=date_to,
        )
        trace.log_parsed({
            "persons": parsed.persons,
            "locations": parsed.locations,
            "date_from": parsed.date_from,
            "date_to": parsed.date_to,
            "relevant_collections": parsed.relevant_collections,
            "query_type": analyzed.query_type,
            "complexity": analyzed.complexity,
        })
        yield _sse("query_analysis", {
            "query": query,
            "persons": parsed.persons or analyzed.entities or [],
            "locations": parsed.locations or [],
            "date_from": effective_date_from,
            "date_to": effective_date_to,
            "query_type": analyzed.query_type,
            "complexity": analyzed.complexity,
            "relevant_collections": parsed.relevant_collections,
        })

        # ── Phase 2: Retrieval ───────────────────────────────────────────────
        if show_thoughts:
            coll_hint = collections or parsed.relevant_collections or ["photos", "messages", "reviews"]
            yield _sse("thought", f"Starte Suche in {len(coll_hint)} Collections")

        yield _sse("retrieval", {"status": "in_progress", "message": "Durchsuche Datenbanken..."})
        await asyncio.sleep(0)  # Flush — kritisch für Real-Time UX!

        retrieval_params: RetrievalParams = {
            "date_from": effective_date_from,
            "date_to": effective_date_to,
            "keywords": parsed.schluesselwoerter,
            "persons": person_names or parsed.persons,
            "locations": location_names or parsed.locations,
            "collections": collections or parsed.relevant_collections or None,
        }
        semantic_sources, kw_sources = await _phase_retrieve(
            query=query,
            user_id=user_id,
            params=retrieval_params,
            n_per_collection=n_per_collection,
            min_score=min_score,
        )

        trace.log_retrieval(semantic_sources)
        yield _sse("retrieval", {
            "status": "completed",
            "total_sources": len(semantic_sources),
            "keyword_sources": len(kw_sources),
            "collections": list({s["collection"] for s in semantic_sources}),
            "top_score": round(semantic_sources[0]["score"], 2) if semantic_sources else 0.0,
        })

        # ── Phase 3: Empty-Result Guard ──────────────────────────────────────
        if not semantic_sources and not kw_sources and _has_strict_date_filter(analyzed):
            no_results_msg = _generate_no_results_message(query, analyzed)
            yield _sse("text", no_results_msg)
            yield _sse("sources", [])
            trace.finish(no_results_msg)
            return

        # ── Phase 4: Context Compression ─────────────────────────────────────
        total = len(semantic_sources) + len(kw_sources)
        if show_thoughts and total > 10:
            yield _sse("thought", f"Komprimiere {total} Quellen für optimale Token-Nutzung")

        context = _phase_compress(semantic_sources, kw_sources)

        # ── Phase 5: Prompt aufbauen ─────────────────────────────────────────
        messages = _phase_build_messages(query, context, chat_history)

        # ── Phase 6: Generierung ─────────────────────────────────────────────
        initial_ids = {s["id"] for s in semantic_sources + kw_sources}
        retrieval_fn, thinking_sources = build_retrieval_fn(
            query, user_id, retrieval_params, initial_source_ids=initial_ids
        )

        # Thinking-Trace Closure
        _qid = trace.query_id
        def _trace_fn(data: dict) -> None:
            from backend.rag.query_logger import log_thinking_iteration
            log_thinking_iteration(query_id=_qid, **data)

        async for chunk in _phase_generate(
            messages=messages,
            context=context,
            query=query,
            retrieval_fn=retrieval_fn,
            use_thinking_mode=use_thinking_mode,
            thinking_max_iterations=thinking_max_iterations,
            show_thoughts=show_thoughts,
            trace_fn=_trace_fn,
        ):
            event = json.loads(chunk)
            if event.get("type") == "text":
                llm_answer_parts.append(event.get("content", ""))
            yield chunk + "\n\n"

        # ── Phase 7: Sources + Trace ─────────────────────────────────────────
        # Im Thinking Mode entsprechen [[n]]-Referenzen in der Antwort den
        # zuletzt re-retrievten Quellen, nicht den initialen semantischen.
        # thinking_sources enthält diese Quellen in compress_sources-Reihenfolge.
        # Im Standard-Modus: semantic_sources score-sortiert (wie compress_sources),
        # damit [[n]] auch dort korrekt auf _lastSources[n-1] zeigt.
        if thinking_sources:
            display_sources = thinking_sources
        else:
            sorted_sem = sorted(semantic_sources, key=lambda s: s.get("score", 0), reverse=True)
            display_sources = sorted_sem + kw_sources
        yield _sse("sources", _format_sources(display_sources[:MAX_SOURCES_DISPLAY]))

        llm_cfg = get_cfg()
        trace.log_provider(llm_cfg.get("provider", ""), llm_cfg.get("model", ""))
        trace.log_prompts(
            messages[0]["content"] if messages else "",
            messages[-1]["content"] if messages else "",
        )
        trace.finish("".join(llm_answer_parts))

    except Exception as exc:
        logger.exception("Fehler in answer_v3_stream")
        trace.finish(f"[ERROR] {exc}")
        yield _sse("error", str(exc)) + "\n\n"


# ============================================================================
# PHASE-FUNKTIONEN (SRP: je eine klar benannte Aufgabe)
# ============================================================================

async def _phase_parse(
    query: str,
    chat_history: list[dict] | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[ParsedQuery, Any, str | None, str | None]:
    """
    Phase 1: LLM-basiertes Query-Parsing + Query-Analyse.

    Returns:
        (parsed, analyzed, effective_date_from, effective_date_to)
    """
    parsed = parse_query(query, chat_history=chat_history)
    analyzed = analyze_query(query)
    effective_date_from = date_from or parsed.date_from
    effective_date_to = date_to or parsed.date_to
    if effective_date_from or effective_date_to:
        logger.info("Temporal filter: %s – %s", effective_date_from, effective_date_to)
    return parsed, analyzed, effective_date_from, effective_date_to


async def _phase_retrieve(
    query: str,
    user_id: str,
    params: RetrievalParams,
    n_per_collection: int,
    min_score: float,
) -> tuple[list[Source], list[Source]]:
    """
    Phase 2: Hybrid-Retrieval via retrieval.retrieve().

    Returns:
        (semantic_sources, keyword_sources) — dedupliziert.
    """
    return retrieve(
        query=query,
        user_id=user_id,
        params=params,
        n_per_collection=n_per_collection,
        min_score=min_score,
    )


def _phase_compress(
    semantic_sources: list[Source],
    kw_sources: list[Source],
) -> str:
    """
    Phase 3: Context Compression.

    Semantische Quellen score-sortiert (FULL/COMPACT/MINIMAL),
    Keyword-Quellen als eigener chronologischer Block.
    """
    return compress_sources(
        semantic_sources,
        budget=ContextBudget(max_tokens=DEFAULT_TOKEN_BUDGET),
        top_n_full=TOP_N_FULL,
        keyword_sources=kw_sources or None,
    )


def _phase_build_messages(
    query: str,
    context: str,
    chat_history: list[dict] | None,
) -> list[dict]:
    """
    Phase 4: LLM-Nachrichten zusammenstellen.

    System-Prompt + optionale Chat-History (max MAX_CHAT_HISTORY) + Query+Kontext.
    """
    messages: list[dict] = [
        {"role": "system", "content": _get_system_prompt_v3()},
    ]
    if chat_history:
        for msg in chat_history[-MAX_CHAT_HISTORY:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({
        "role": "user",
        "content": f"ANFRAGE: {query}\n\nKONTEXT:\n{context}",
    })
    return messages


async def _phase_generate(
    messages: list[dict],
    context: str,
    query: str,
    retrieval_fn: RetrievalFn,
    use_thinking_mode: bool,
    thinking_max_iterations: int,
    show_thoughts: bool,
    trace_fn: Callable[[dict], None] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Phase 5: LLM-Generierung.

    Thinking Mode (Standard): Researcher → Challenger → Decider mit aktivem
    Nachforschen via retrieval_fn.

    Standard Mode: Direkter LLM-Call via chat_stream.

    Yields JSON-Strings (ohne trailing \\n\\n).
    """
    if use_thinking_mode:
        if show_thoughts:
            yield _sse_raw("thought", "Aktiviere Thinking Mode — Researcher, Challenger und Decider analysieren die Quellen")

        async for ev in thinking_mode_stream(
            query=query,
            context=context,
            max_iterations=thinking_max_iterations,
            retrieval_fn=retrieval_fn,
            trace_fn=trace_fn,
        ):
            yield ev

    else:
        if show_thoughts:
            yield _sse_raw("thought", "Generiere Antwort basierend auf gefundenen Quellen")

        async for event in chat_stream(messages):
            if event["type"] == "text":
                yield _sse_raw("text", event["content"])
            elif event["type"] in ("thought", "tool_call", "tool_result"):
                yield _sse_raw(event["type"], event["content"])


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

def _format_sources(sources: list[Source]) -> list[dict]:
    """Formatiert Quellen für den Frontend-Transport (gekürzt, serialisierbar)."""
    return [
        {
            "id": s["id"],
            "collection": s["collection"],
            "score": round(s["score"], 2),
            "document": s["document"][:500],
            "metadata": s["metadata"],
        }
        for s in sources
    ]


def _sse(event_type: str, content: Any) -> str:
    """SSE-Event mit trailing \\n\\n (für direktes yield in answer_v3_stream)."""
    return json.dumps({"type": event_type, "content": content}, ensure_ascii=False) + "\n\n"


def _sse_raw(event_type: str, content: Any) -> str:
    """SSE-Event OHNE trailing \\n\\n (für yield in _phase_generate, wird oben ergänzt)."""
    return json.dumps({"type": event_type, "content": content}, ensure_ascii=False)
