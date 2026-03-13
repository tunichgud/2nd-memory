#!/usr/bin/env python3
"""
export_test_cases.py – Exportiert Test-Cases aus query_logs.db als JSON-Fixtures.

Nur Queries mit gesetzter golden_answer werden exportiert.
Die Dateien landen in tests/fixtures/rag_test_cases/{query_id}.json
und sind damit versionierbar (git-tracked).

Verwendung:
  python scripts/export_test_cases.py               # alle exportieren
  python scripts/export_test_cases.py --overwrite   # vorhandene überschreiben
  python scripts/export_test_cases.py --id q_abc123 # nur einen exportieren
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "tests" / "fixtures" / "rag_test_cases"


def export_all(overwrite: bool = False, only_id: str | None = None) -> int:
    from backend.rag.query_logger import _get_db_path, _init_once, get_query, get_latest_eval
    import sqlite3

    _init_once()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(_get_db_path()), check_same_thread=False) as conn:
        if only_id:
            rows = conn.execute(
                "SELECT DISTINCT q.query_id FROM rag_queries q "
                "JOIN rag_eval e ON q.query_id = e.query_id "
                "WHERE e.golden_answer IS NOT NULL AND q.query_id = ?",
                (only_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT q.query_id FROM rag_queries q "
                "JOIN rag_eval e ON q.query_id = e.query_id "
                "WHERE e.golden_answer IS NOT NULL AND e.golden_answer != '' "
                "ORDER BY q.created_at DESC"
            ).fetchall()

    exported = skipped = 0
    for (qid,) in rows:
        target = OUTPUT_DIR / f"{qid}.json"
        if target.exists() and not overwrite:
            print(f"  skip  {qid}  (bereits vorhanden, --overwrite zum Überschreiben)")
            skipped += 1
            continue

        q  = get_query(qid)
        ev = get_latest_eval(qid)
        if not q or not ev:
            continue

        test_case = {
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
                "provider": q.get("llm_provider"),
            },
        }

        target.write_text(json.dumps(test_case, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  export {qid}  verdict={ev.get('verdict')}  score={ev.get('score', 0):.2f}  sources={len(q.get('sources_retrieved') or [])}")
        exported += 1

    print(f"\n✅ {exported} exportiert, {skipped} übersprungen → {OUTPUT_DIR}")
    return exported


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export RAG test cases from DB to JSON fixtures")
    parser.add_argument("--overwrite", action="store_true", help="Vorhandene Dateien überschreiben")
    parser.add_argument("--id", dest="only_id", default=None, help="Nur diese query_id exportieren")
    args = parser.parse_args()

    count = export_all(overwrite=args.overwrite, only_id=args.only_id)
    sys.exit(0 if count >= 0 else 1)
