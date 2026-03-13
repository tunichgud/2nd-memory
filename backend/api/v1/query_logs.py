"""
query_logs.py – REST API für RAG Query Logs, Evaluation und Test-Export.

Endpunkte:
  GET  /api/v1/query-logs                      Liste der letzten Queries
  GET  /api/v1/query-logs/{query_id}           Vollständiger Trace
  GET  /api/v1/query-logs/{query_id}/eval      Letztes Evaluationsergebnis
  POST /api/v1/query-logs/{query_id}/golden    Referenzantwort + Auto-Eval
  POST /api/v1/query-logs/{query_id}/evaluate  Manuelle Evaluation
  POST /api/v1/query-logs/{query_id}/replay    Hermetic/Integration Replay
  POST /api/v1/query-logs/eval/batch           Batch-Replay für Modellvergleich
  GET  /api/v1/query-logs/export/test-suite    Alle Test-Cases als JSON
"""
from __future__ import annotations

import json
import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/query-logs", tags=["v1/query-logs"])


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class GoldenRequest(BaseModel):
    golden_answer: str
    required_facts: list[str] = []
    forbidden_facts: list[str] = []
    method: Literal["embedding_only", "llm_judge", "combined"] = "combined"


class EvaluateRequest(BaseModel):
    golden_answer: str
    required_facts: list[str] = []
    forbidden_facts: list[str] = []
    method: Literal["embedding_only", "llm_judge", "combined"] = "combined"


class ReplayRequest(BaseModel):
    mode: Literal["hermetic", "integration"] = "hermetic"
    override_model: str | None = None


class BatchCompareRequest(BaseModel):
    model_a: str
    model_b: str
    query_ids: list[str] | Literal["all"] = "all"
    mode: Literal["hermetic", "integration"] = "hermetic"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _require_query(query_id: str) -> dict:
    from backend.rag.query_logger import get_query
    q = get_query(query_id)
    if not q:
        raise HTTPException(status_code=404, detail=f"Query '{query_id}' nicht gefunden")
    return q


def _replay_with_sources(
    query: str,
    sources: list[dict],
    system_prompt: str,
    model: str | None = None,
) -> str:
    """Führt einen LLM-Call mit gegebenen Sources durch (kein ChromaDB-Lookup)."""
    from backend.rag.retriever_v2 import _format_sources_for_llm
    from backend.llm.connector import chat, get_cfg

    cfg = get_cfg()
    use_model = model or cfg["llm"]["model"]

    context = _format_sources_for_llm(sources, use_compression=len(sources) > 10)
    user_prompt = (
        f"NUTZERANFRAGE:\n{query}\n\n"
        f"KONTEXT AUS DER DATENBANK:\n{context}\n\n"
        f"ANWEISUNG:\nBeantworte die Frage ausschließlich auf Basis des Kontexts."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return chat(messages, model=use_model)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_query_logs(limit: int = 50, offset: int = 0):
    """Liste der letzten RAG-Queries (ohne große Felder)."""
    from backend.rag.query_logger import list_queries
    queries = list_queries(limit=limit, offset=offset)
    return {"total": len(queries), "offset": offset, "queries": queries}


@router.get("/{query_id}")
async def get_query_log(query_id: str):
    """Vollständiger Trace einer Query inkl. Sources, Tool-Calls, Prompts."""
    q = _require_query(query_id)
    from backend.rag.query_logger import get_latest_eval
    q["latest_eval"] = get_latest_eval(query_id)
    return q


@router.get("/{query_id}/eval")
async def get_evaluation(query_id: str):
    """Letztes Evaluationsergebnis für eine Query."""
    _require_query(query_id)
    from backend.rag.query_logger import get_latest_eval
    ev = get_latest_eval(query_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Noch keine Evaluation vorhanden. POST /golden zuerst.")
    return ev


@router.post("/{query_id}/golden")
async def set_golden_answer(query_id: str, req: GoldenRequest):
    """
    Setzt die Referenzantwort und startet automatisch eine semantische Evaluation.

    Die Evaluation vergleicht die gespeicherte LLM-Antwort inhaltlich
    gegen die Referenz – nicht auf exakte Übereinstimmung.
    """
    q = _require_query(query_id)
    generated = q.get("llm_answer", "")
    if not generated:
        raise HTTPException(status_code=422, detail="Query hat noch keine LLM-Antwort gespeichert")

    from backend.rag.evaluator import evaluate, save_evaluation
    eval_result = evaluate(
        query=q["raw_query"],
        golden_answer=req.golden_answer,
        generated_answer=generated,
        method=req.method,
        required_facts=req.required_facts,
        forbidden_facts=req.forbidden_facts,
    )
    eval_id = save_evaluation(
        query_id=query_id,
        golden_answer=req.golden_answer,
        eval_result=eval_result,
        required_facts=req.required_facts,
        forbidden_facts=req.forbidden_facts,
    )

    return {
        "query_id": query_id,
        "eval_id": eval_id,
        "verdict": eval_result["verdict"],
        "score": eval_result["score"],
        "embedding_similarity": eval_result.get("embedding_similarity"),
        "missing_facts": eval_result.get("missing_facts", []),
        "wrong_facts": eval_result.get("wrong_facts", []),
        "judge_reasoning": eval_result.get("judge_reasoning", ""),
        "eval_method": eval_result.get("eval_method"),
    }


@router.post("/{query_id}/evaluate")
async def evaluate_query(query_id: str, req: EvaluateRequest):
    """
    Führt eine manuelle Evaluation durch (ohne golden_answer zu persistieren).
    Nützlich zum schnellen Testen verschiedener Methoden.
    """
    q = _require_query(query_id)
    generated = q.get("llm_answer", "")
    if not generated:
        raise HTTPException(status_code=422, detail="Query hat noch keine LLM-Antwort gespeichert")

    from backend.rag.evaluator import evaluate
    return evaluate(
        query=q["raw_query"],
        golden_answer=req.golden_answer,
        generated_answer=generated,
        method=req.method,
        required_facts=req.required_facts,
        forbidden_facts=req.forbidden_facts,
    )


@router.post("/{query_id}/replay")
async def replay_query(query_id: str, req: ReplayRequest):
    """
    Spielt eine Query erneut ab und vergleicht mit der ursprünglichen Antwort.

    Modus hermetic: Nutzt den gespeicherten Source-Snapshot (kein ChromaDB-Lookup).
                    Testet nur LLM + Prompt-Qualität, isoliert von Datenbankänderungen.

    Modus integration: Fragt ChromaDB live ab (wie normaler Betrieb).
                       Testet die gesamte Pipeline.
    """
    import asyncio
    q = _require_query(query_id)

    original_answer = q.get("llm_answer", "")
    system_prompt = q.get("system_prompt", "")
    raw_query = q["raw_query"]

    if req.mode == "hermetic":
        sources = q.get("sources_retrieved") or []
        if not sources:
            raise HTTPException(status_code=422, detail="Kein Source-Snapshot gespeichert – hermetic Replay nicht möglich")
        loop = asyncio.get_event_loop()
        new_answer = await loop.run_in_executor(
            None,
            lambda: _replay_with_sources(raw_query, sources, system_prompt, req.override_model),
        )
    else:
        # Integration: volle Pipeline
        from backend.rag.retriever_v2 import answer_v2
        from backend.db.database import DEFAULT_USER_ID
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: answer_v2(
                masked_query=raw_query,
                user_id=DEFAULT_USER_ID,
                person_tokens=[],
                location_tokens=[],
            ),
        )
        new_answer = result.get("answer", "")

    # Wenn golden vorhanden: automatisch auswerten
    from backend.rag.query_logger import get_latest_eval
    from backend.rag.evaluator import evaluate as eval_fn
    latest_eval = get_latest_eval(query_id)

    evaluation = None
    if latest_eval and latest_eval.get("golden_answer"):
        evaluation = eval_fn(
            query=raw_query,
            golden_answer=latest_eval["golden_answer"],
            generated_answer=new_answer,
            method="combined",
            required_facts=latest_eval.get("required_facts") or [],
            forbidden_facts=latest_eval.get("forbidden_facts") or [],
        )

    score_delta = None
    if evaluation and latest_eval:
        orig_score = latest_eval.get("score") or 0.0
        score_delta = round(evaluation.get("score", 0.0) - orig_score, 3)

    return {
        "query_id": query_id,
        "mode": req.mode,
        "override_model": req.override_model,
        "original_answer": original_answer,
        "new_answer": new_answer,
        "evaluation": evaluation,
        "score_delta": score_delta,
    }


@router.post("/eval/batch")
async def batch_compare(req: BatchCompareRequest):
    """
    Vergleicht zwei Modelle auf allen (oder ausgewählten) Test-Cases mit golden_answer.

    Beide Modelle werden im hermetic Modus gegen den Source-Snapshot getestet.
    Gibt Pass-Rate, Avg-Score und Latenz pro Modell zurück.
    """
    import asyncio
    import sqlite3
    from backend.rag.query_logger import _get_db_path, _init_once, get_query
    from backend.rag.evaluator import evaluate as eval_fn

    _init_once()

    # Query-IDs ermitteln
    if req.query_ids == "all":
        with sqlite3.connect(str(_get_db_path()), check_same_thread=False) as conn:
            rows = conn.execute("""
                SELECT DISTINCT q.query_id
                FROM rag_queries q
                JOIN rag_eval e ON q.query_id = e.query_id
                WHERE e.golden_answer IS NOT NULL AND e.golden_answer != ''
            """).fetchall()
        query_ids = [r[0] for r in rows]
    else:
        query_ids = req.query_ids

    if not query_ids:
        raise HTTPException(status_code=404, detail="Keine Test-Cases mit golden_answer gefunden")

    results_a, results_b = [], []
    loop = asyncio.get_event_loop()

    for qid in query_ids:
        q = get_query(qid)
        if not q:
            continue
        sources = q.get("sources_retrieved") or []
        if not sources:
            continue
        system_prompt = q.get("system_prompt", "")
        raw_query = q["raw_query"]

        # Golden holen
        from backend.rag.query_logger import get_latest_eval
        ev = get_latest_eval(qid)
        if not ev or not ev.get("golden_answer"):
            continue
        golden = ev["golden_answer"]
        rf = ev.get("required_facts") or []
        ff = ev.get("forbidden_facts") or []

        for model, result_list in [(req.model_a, results_a), (req.model_b, results_b)]:
            t0 = time.time()
            try:
                answer = await loop.run_in_executor(
                    None,
                    lambda m=model: _replay_with_sources(raw_query, sources, system_prompt, m),
                )
                latency_ms = int((time.time() - t0) * 1000)
                ev_result = eval_fn(
                    query=raw_query,
                    golden_answer=golden,
                    generated_answer=answer,
                    method="combined",
                    required_facts=rf,
                    forbidden_facts=ff,
                )
                result_list.append({
                    "query_id": qid,
                    "verdict": ev_result["verdict"],
                    "score": ev_result.get("score", 0.0),
                    "latency_ms": latency_ms,
                })
            except Exception as exc:
                result_list.append({
                    "query_id": qid,
                    "verdict": "ERROR",
                    "score": 0.0,
                    "latency_ms": 0,
                    "error": str(exc),
                })

    def summarize(results: list[dict], model: str) -> dict:
        if not results:
            return {"model": model, "tested": 0, "pass_rate": 0, "avg_score": 0, "avg_latency_ms": 0}
        passed = sum(1 for r in results if r["verdict"] == "PASS")
        return {
            "model": model,
            "tested": len(results),
            "pass_rate": round(passed / len(results), 3),
            "avg_score": round(sum(r["score"] for r in results) / len(results), 3),
            "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / len(results)),
            "details": results,
        }

    summary_a = summarize(results_a, req.model_a)
    summary_b = summarize(results_b, req.model_b)
    winner = req.model_a if summary_a["avg_score"] >= summary_b["avg_score"] else req.model_b

    return {
        "model_a": summary_a,
        "model_b": summary_b,
        "winner": winner,
        "test_cases": len(query_ids),
    }


@router.get("/export/test-suite")
async def export_test_suite():
    """
    Exportiert alle Test-Cases mit golden_answer als JSON.

    Jeder Test-Case enthält:
    - query + golden_answer + required_facts + forbidden_facts
    - Source-Snapshot (für hermetic Replay)
    - Letztes Evaluationsergebnis
    """
    import sqlite3
    from backend.rag.query_logger import _get_db_path, _init_once, get_query, get_latest_eval
    _init_once()

    with sqlite3.connect(str(_get_db_path()), check_same_thread=False) as conn:
        rows = conn.execute("""
            SELECT DISTINCT q.query_id
            FROM rag_queries q
            JOIN rag_eval e ON q.query_id = e.query_id
            WHERE e.golden_answer IS NOT NULL AND e.golden_answer != ''
            ORDER BY q.created_at DESC
        """).fetchall()

    test_cases = []
    for (qid,) in rows:
        q = get_query(qid)
        ev = get_latest_eval(qid)
        if not q or not ev:
            continue
        test_cases.append({
            "test_id": qid,
            "query": q["raw_query"],
            "snapshot": {
                "captured_at": q["created_at"],
                "sources": q.get("sources_retrieved") or [],
                "system_prompt": q.get("system_prompt", ""),
                "parsed_query": q.get("parsed_query"),
            },
            "golden": {
                "answer": ev["golden_answer"],
                "required_facts": ev.get("required_facts") or [],
                "forbidden_facts": ev.get("forbidden_facts") or [],
                "set_by": ev.get("set_by", "user"),
                "set_at": ev.get("evaluated_at"),
            },
            "last_eval": {
                "verdict": ev.get("verdict"),
                "score": ev.get("score"),
                "embedding_similarity": ev.get("embedding_similarity"),
                "missing_facts": ev.get("missing_facts") or [],
                "wrong_facts": ev.get("wrong_facts") or [],
                "eval_method": ev.get("eval_method"),
                "model": q.get("llm_model"),
            },
        })

    return JSONResponse(
        content={"test_suite_version": "1.0", "total": len(test_cases), "test_cases": test_cases},
        headers={"Content-Disposition": "attachment; filename=2nd_memory_test_suite.json"},
    )
