"""
evaluator.py – Semantische Evaluation von RAG-Antworten.

Vergleicht eine generierte Antwort gegen eine Referenzantwort auf inhaltliche
Korrektheit – nicht auf exakte String-Übereinstimmung.

Drei Methoden:
  embedding_only  Cosinus-Ähnlichkeit der Embeddings (schnell, ~50ms)
  llm_judge       LLM bewertet ob Fakten übereinstimmen (präzise, ~2s)
  combined        Erst Embedding, LLM-Judge nur bei Grenzfällen (0.65–0.85)
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
import uuid

logger = logging.getLogger(__name__)

_EMBED_PASS_THRESHOLD = 0.85
_EMBED_FAIL_THRESHOLD = 0.65


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _eval_by_embedding(golden: str, generated: str) -> dict:
    from backend.rag.embedder import embed_texts
    vecs = embed_texts([golden, generated])
    sim = _cosine_similarity(vecs[0], vecs[1])
    if sim >= _EMBED_PASS_THRESHOLD:
        verdict = "PASS"
    elif sim >= _EMBED_FAIL_THRESHOLD:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"
    return {
        "embedding_similarity": round(sim, 4),
        "verdict": verdict,
        "score": round(sim, 4),
        "missing_facts": [],
        "wrong_facts": [],
        "judge_reasoning": f"Embedding-Similarity: {sim:.2f}",
        "eval_method": "embedding_only",
    }


def _eval_by_llm(
    query: str,
    golden: str,
    generated: str,
    required_facts: list[str],
    forbidden_facts: list[str],
) -> dict:
    from backend.llm.connector import chat, get_cfg
    required_hint = f"\nPflicht-Fakten (müssen enthalten sein): {required_facts}" if required_facts else ""
    forbidden_hint = f"\nVerbotene Fakten (dürfen NICHT vorkommen): {forbidden_facts}" if forbidden_facts else ""

    prompt = f"""Du bist ein Evaluator für ein RAG-System. Bewerte ob die generierte Antwort inhaltlich korrekt ist.

NUTZERANFRAGE: {query}

REFERENZANTWORT (Inhalt muss stimmen, exakte Formulierung egal):
{golden}{required_hint}{forbidden_hint}

GENERIERTE ANTWORT:
{generated}

Antworte NUR mit validem JSON ohne Markdown-Wrapper:
{{
  "verdict": "PASS",
  "score": 0.95,
  "missing_facts": [],
  "wrong_facts": [],
  "reasoning": "Kurze Begründung auf Deutsch"
}}

Bewertungsregel:
PASS    = alle wichtigen Fakten korrekt und vollständig
PARTIAL = teilweise korrekt, wichtige Fakten fehlen oder ungenau
FAIL    = falsche Fakten enthalten oder komplett am Thema vorbei"""

    cfg = get_cfg()
    start = int(time.time() * 1000)
    try:
        raw = chat([{"role": "user", "content": prompt}], model=cfg["llm"]["model"])
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise ValueError(f"Kein JSON in LLM-Antwort: {raw[:200]}")
        result = json.loads(match.group())
        return {
            "embedding_similarity": None,
            "verdict": result.get("verdict", "PARTIAL"),
            "score": float(result.get("score", 0.5)),
            "missing_facts": result.get("missing_facts", []),
            "wrong_facts": result.get("wrong_facts", []),
            "judge_reasoning": result.get("reasoning", ""),
            "eval_method": "llm_judge",
            "eval_duration_ms": int(time.time() * 1000) - start,
        }
    except Exception as exc:
        logger.error("LLM-Judge fehlgeschlagen: %s", exc)
        return {
            "embedding_similarity": None,
            "verdict": "PARTIAL",
            "score": 0.5,
            "missing_facts": [],
            "wrong_facts": [],
            "judge_reasoning": f"Evaluierung fehlgeschlagen: {exc}",
            "eval_method": "llm_judge",
            "eval_duration_ms": int(time.time() * 1000) - start,
        }


def evaluate(
    query: str,
    golden_answer: str,
    generated_answer: str,
    method: str = "combined",
    required_facts: list[str] | None = None,
    forbidden_facts: list[str] | None = None,
) -> dict:
    """
    Evaluiert eine generierte Antwort inhaltlich gegen eine Referenzantwort.

    Args:
        query:            Ursprüngliche Nutzeranfrage
        golden_answer:    Referenzantwort (inhaltlich korrekt)
        generated_answer: Vom LLM generierte Antwort
        method:           "embedding_only" | "llm_judge" | "combined"
        required_facts:   Fakten die zwingend enthalten sein müssen
        forbidden_facts:  Fakten die nicht enthalten sein dürfen (z.B. halluzinierte Namen)

    Returns:
        Dict mit verdict (PASS/PARTIAL/FAIL), score (0–1), missing_facts, wrong_facts, reasoning
    """
    start = int(time.time() * 1000)
    rf = required_facts or []
    ff = forbidden_facts or []

    if method == "embedding_only":
        result = _eval_by_embedding(golden_answer, generated_answer)

    elif method == "llm_judge":
        result = _eval_by_llm(query, golden_answer, generated_answer, rf, ff)

    else:  # combined
        embed_result = _eval_by_embedding(golden_answer, generated_answer)
        sim = embed_result["embedding_similarity"]

        if sim >= _EMBED_PASS_THRESHOLD and not rf and not ff:
            result = embed_result
            result["eval_method"] = "combined_embed_only"
        else:
            llm_result = _eval_by_llm(query, golden_answer, generated_answer, rf, ff)
            llm_result["embedding_similarity"] = sim
            llm_result["eval_method"] = "combined"
            result = llm_result

    # Forbidden facts immer hart prüfen, unabhängig von LLM-Urteil
    if ff and generated_answer:
        gen_lower = generated_answer.lower()
        found_forbidden = [f for f in ff if f.lower() in gen_lower]
        if found_forbidden:
            result["verdict"] = "FAIL"
            result["wrong_facts"] = list(set(result.get("wrong_facts", []) + found_forbidden))
            result["score"] = min(result.get("score", 0.5), 0.2)

    result.setdefault("eval_duration_ms", int(time.time() * 1000) - start)
    return result


def save_evaluation(
    query_id: str,
    golden_answer: str,
    eval_result: dict,
    required_facts: list[str] | None = None,
    forbidden_facts: list[str] | None = None,
) -> str:
    """Speichert Evaluationsergebnis in query_logs.db. Gibt eval_id zurück."""
    import sqlite3
    from backend.rag.query_logger import _get_db_path, _init_once
    _init_once()

    eval_id = f"ev_{uuid.uuid4().hex[:10]}"
    with sqlite3.connect(str(_get_db_path()), check_same_thread=False) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO rag_eval
            (eval_id, query_id, golden_answer, required_facts, forbidden_facts,
             embedding_similarity, verdict, score, missing_facts, wrong_facts,
             judge_reasoning, eval_method, eval_duration_ms, evaluated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            eval_id,
            query_id,
            golden_answer,
            json.dumps(required_facts or [], ensure_ascii=False),
            json.dumps(forbidden_facts or [], ensure_ascii=False),
            eval_result.get("embedding_similarity"),
            eval_result.get("verdict"),
            eval_result.get("score"),
            json.dumps(eval_result.get("missing_facts", []), ensure_ascii=False),
            json.dumps(eval_result.get("wrong_facts", []), ensure_ascii=False),
            eval_result.get("judge_reasoning", ""),
            eval_result.get("eval_method", ""),
            eval_result.get("eval_duration_ms", 0),
            time.strftime("%Y-%m-%dT%H:%M:%S"),
        ))
    logger.info("Evaluation gespeichert: %s → %s (score=%.2f)",
                eval_id, eval_result.get("verdict"), eval_result.get("score", 0))
    return eval_id
