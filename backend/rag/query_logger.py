"""
query_logger.py – Strukturiertes Logging jeder RAG-Anfrage.

Speichert Query, Parsing, Retrieved Sources, Tool-Calls, Prompts und Antwort
in einer separaten SQLite-DB (data/query_logs.db) für Debugging und Test-Generierung.

Jede Anfrage bekommt eine eindeutige query_id (z.B. q_20260311_143512_a3f7).
Die gespeicherten Source-Snapshots ermöglichen hermetic Replay-Tests ohne live ChromaDB.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_db_path: Path | None = None
_schema_initialized = False


def _get_db_path() -> Path:
    global _db_path
    if _db_path is not None:
        return _db_path
    base = Path(__file__).resolve().parents[2]
    with open(base / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    data_dir = base / cfg["paths"]["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "query_logs.db"
    return _db_path


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rag_queries (
                query_id          TEXT PRIMARY KEY,
                created_at        TEXT NOT NULL,
                raw_query         TEXT NOT NULL,
                parsed_query      TEXT,
                sources_retrieved TEXT,
                tool_calls        TEXT,
                llm_provider      TEXT,
                llm_model         TEXT,
                system_prompt     TEXT,
                user_prompt       TEXT,
                llm_answer        TEXT,
                total_duration_ms INTEGER,
                source_count      INTEGER DEFAULT 0,
                hallucination_risk TEXT DEFAULT 'unknown'
            );

            CREATE TABLE IF NOT EXISTS thinking_traces (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id              TEXT NOT NULL,
                iteration             INTEGER NOT NULL,
                researcher_output     TEXT,
                challenger_output     TEXT,
                decider_decision      TEXT,
                decider_reasoning     TEXT,
                retrieval_keywords    TEXT,
                retrieval_date_from   TEXT,
                retrieval_date_to     TEXT,
                retrieval_found_count INTEGER,
                context_size_before   INTEGER,
                context_size_after    INTEGER,
                accumulated_facts_size INTEGER,
                created_at            TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rag_eval (
                eval_id              TEXT PRIMARY KEY,
                query_id             TEXT NOT NULL REFERENCES rag_queries(query_id),
                golden_answer        TEXT NOT NULL,
                required_facts       TEXT,
                forbidden_facts      TEXT,
                embedding_similarity REAL,
                verdict              TEXT,
                score                REAL,
                missing_facts        TEXT,
                wrong_facts          TEXT,
                judge_reasoning      TEXT,
                eval_method          TEXT,
                eval_duration_ms     INTEGER,
                evaluated_at         TEXT,
                set_by               TEXT DEFAULT 'user'
            );
        """)


def _init_once() -> None:
    global _schema_initialized
    if not _schema_initialized:
        _ensure_schema()
        _schema_initialized = True


def _make_query_id() -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"q_{ts}_{short}"


class QueryTrace:
    """Sammelt alle Zwischenschritte einer RAG-Anfrage und persistiert sie am Ende."""

    def __init__(self, query_id: str, raw_query: str):
        self.query_id = query_id
        self.raw_query = raw_query
        self.parsed_query: dict | None = None
        self.sources: list[dict] = []
        self.tool_calls: list[dict] = []
        self.system_prompt: str = ""
        self.user_prompt: str = ""
        self.llm_answer: str = ""
        self.llm_provider: str = ""
        self.llm_model: str = ""
        self._start_ms = int(time.time() * 1000)
        self._tool_start_ms: int | None = None

    def log_parsed(self, parsed: dict) -> None:
        self.parsed_query = parsed

    def log_retrieval(self, sources: list[dict]) -> None:
        """Snapshot der Retrieved Sources – ohne numpy arrays, JSON-serialisierbar."""
        self.sources = [
            {
                "id": s.get("id"),
                "collection": s.get("collection"),
                "document": s.get("document"),
                "metadata": {
                    k: v for k, v in s.get("metadata", {}).items()
                    if isinstance(v, (str, int, float, bool, type(None)))
                },
                "score": s.get("score"),
            }
            for s in sources
        ]

    def start_tool_call(self, tool: str, args: dict) -> None:
        self._tool_start_ms = int(time.time() * 1000)
        self.tool_calls.append({
            "tool": tool,
            "args": {k: v for k, v in args.items() if isinstance(v, (str, int, float, bool, list, type(None)))},
            "result_count": 0,
            "duration_ms": 0,
            "status": "running",
        })

    def finish_tool_call(self, result_count: int, error: str | None = None) -> None:
        if self.tool_calls and self._tool_start_ms is not None:
            call = self.tool_calls[-1]
            call["result_count"] = result_count
            call["duration_ms"] = int(time.time() * 1000) - self._tool_start_ms
            call["status"] = "error" if error else "success"
            if error:
                call["error"] = error

    def log_prompts(self, system_prompt: str, user_prompt: str) -> None:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt

    def log_provider(self, provider: str, model: str) -> None:
        self.llm_provider = provider
        self.llm_model = model

    def finish(self, answer: str) -> None:
        self.llm_answer = answer
        self._save()

    def _estimate_hallucination_risk(self) -> str:
        """Heuristik: Tauchen kapitalisierte Wörter in der Antwort auf,
        die nicht in den retrieved Sources stehen?"""
        if not self.sources or not self.llm_answer:
            return "unknown"
        source_text = " ".join(s.get("document", "") for s in self.sources).lower()
        candidates = re.findall(r'\b[A-ZÄÖÜ][a-zäöüß]{2,}\b', self.llm_answer)
        if not candidates:
            return "low"
        unsupported = [w for w in candidates if w.lower() not in source_text]
        ratio = len(unsupported) / len(candidates)
        if ratio > 0.4:
            return "high"
        elif ratio > 0.2:
            return "medium"
        return "low"

    def _save(self) -> None:
        try:
            _init_once()
            duration_ms = int(time.time() * 1000) - self._start_ms
            risk = self._estimate_hallucination_risk()
            with _get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO rag_queries
                    (query_id, created_at, raw_query, parsed_query, sources_retrieved,
                     tool_calls, llm_provider, llm_model, system_prompt, user_prompt,
                     llm_answer, total_duration_ms, source_count, hallucination_risk)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    self.query_id,
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    self.raw_query,
                    json.dumps(self.parsed_query, ensure_ascii=False) if self.parsed_query else None,
                    json.dumps(self.sources, ensure_ascii=False),
                    json.dumps(self.tool_calls, ensure_ascii=False),
                    self.llm_provider,
                    self.llm_model,
                    self.system_prompt,
                    self.user_prompt,
                    self.llm_answer,
                    duration_ms,
                    len(self.sources),
                    risk,
                ))
            logger.info("QueryTrace gespeichert: %s (%d sources, %dms, risk=%s)",
                        self.query_id, len(self.sources), duration_ms, risk)
        except Exception as exc:
            logger.error("QueryTrace konnte nicht gespeichert werden: %s", exc)


def start_trace(raw_query: str) -> QueryTrace:
    """Startet einen neuen Query-Trace. Gibt das Trace-Objekt zurück."""
    _init_once()
    return QueryTrace(query_id=_make_query_id(), raw_query=raw_query)


def get_query(query_id: str) -> dict | None:
    """Lädt einen Query-Trace aus der DB."""
    _init_once()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM rag_queries WHERE query_id = ?", (query_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for field in ("parsed_query", "sources_retrieved", "tool_calls"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass
    return d


def list_queries(limit: int = 50, offset: int = 0) -> list[dict]:
    """Listet Query-Traces (ohne große Felder) für Übersicht."""
    _init_once()
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT query_id, created_at, raw_query, llm_provider, llm_model,
                   total_duration_ms, source_count, hallucination_risk
            FROM rag_queries
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    return [dict(r) for r in rows]


def log_thinking_iteration(
    query_id: str,
    iteration: int,
    researcher_output: str = "",
    challenger_output: str = "",
    decider_decision: str = "",
    decider_reasoning: str = "",
    retrieval_keywords: list | None = None,
    retrieval_date_from: str | None = None,
    retrieval_date_to: str | None = None,
    retrieval_found_count: int = -1,
    context_size_before: int = 0,
    context_size_after: int = 0,
    accumulated_facts_size: int = 0,
    **_kwargs: Any,
) -> None:
    """Speichert eine Thinking-Mode-Iteration in der DB."""
    _init_once()
    try:
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO thinking_traces
                    (query_id, iteration, researcher_output, challenger_output,
                     decider_decision, decider_reasoning, retrieval_keywords,
                     retrieval_date_from, retrieval_date_to, retrieval_found_count,
                     context_size_before, context_size_after, accumulated_facts_size)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                query_id, iteration, researcher_output, challenger_output,
                decider_decision, decider_reasoning,
                json.dumps(retrieval_keywords) if retrieval_keywords else None,
                retrieval_date_from, retrieval_date_to, retrieval_found_count,
                context_size_before, context_size_after, accumulated_facts_size,
            ))
    except Exception as exc:
        logger.warning("log_thinking_iteration fehlgeschlagen: %s", exc)


def get_latest_eval(query_id: str) -> dict | None:
    """Lädt das neueste Evaluationsergebnis für eine Query."""
    _init_once()
    with _get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM rag_eval
            WHERE query_id = ?
            ORDER BY evaluated_at DESC
            LIMIT 1
        """, (query_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    for field in ("required_facts", "forbidden_facts", "missing_facts", "wrong_facts"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass
    return d
