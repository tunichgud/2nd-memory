#!/usr/bin/env python3
"""
rag_benchmark.py – Vergleicht mehrere LLM-Modelle auf dem RAG-Test-Suite.

Führt alle Test-Cases aus tests/fixtures/rag_test_cases/ gegen jedes angegebene
Modell im hermetic Modus aus und erzeugt einen Vergleichsreport.

Score-Berechnung:
  PASS    = 1.0
  PARTIAL = 0.5 (gewichtet mit tatsächlichem eval score)
  FAIL    = 0.0

Ausgabe:
  - Tabelle im Terminal
  - JSON-Report in reports/benchmark_{timestamp}.json

Verwendung:
  # Standard-Modell aus config.yaml testen:
  python scripts/rag_benchmark.py

  # Mehrere Modelle vergleichen (Ollama):
  python scripts/rag_benchmark.py --models phi4,qwen3:latest,llama3.2

  # Provider-Mix:
  python scripts/rag_benchmark.py --models "ollama:phi4,openai:gpt-4o,gemini:gemini-2.0-flash"

  # Einzelnen Test-Case debuggen:
  python scripts/rag_benchmark.py --models phi4 --case q_20260311_143512_a3f7
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

FIXTURES_DIR = BASE_DIR / "tests" / "fixtures" / "rag_test_cases"
REPORTS_DIR  = BASE_DIR / "reports"


@contextmanager
def model_override(provider: str | None, model: str | None):
    if not provider and not model:
        yield
        return
    import copy
    import backend.llm.connector as conn
    if conn._cfg is None:
        conn.get_cfg()
    original  = conn._cfg
    patched   = copy.deepcopy(original)
    if provider:
        patched["llm"]["provider"] = provider
    if model:
        patched["llm"]["model"] = model
    conn._cfg = patched
    try:
        yield
    finally:
        conn._cfg = original


def _load_test_cases(only_id: str | None = None) -> list[dict]:
    cases = []
    if not FIXTURES_DIR.exists():
        return cases
    pattern = f"{only_id}.json" if only_id else "*.json"
    for f in sorted(FIXTURES_DIR.glob(pattern)):
        try:
            cases.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"  ⚠️  Fehler beim Laden von {f.name}: {e}")
    return cases


def _run_case(case: dict, provider: str | None, model: str | None) -> dict:
    from backend.rag.retriever_v2 import _format_sources_for_llm, _get_system_prompt
    from backend.llm.connector import chat
    from backend.rag.evaluator import evaluate

    query          = case["query"]
    sources        = case["snapshot"].get("sources", [])
    # Nutze immer den aktuellen System-Prompt (nicht den gespeicherten Snapshot),
    # damit Prompt-Verbesserungen sofort in den Benchmark-Ergebnissen sichtbar sind.
    system_prompt  = _get_system_prompt()
    golden         = case["golden"]["answer"]
    required_facts = case["golden"].get("required_facts", [])
    forbidden_facts= case["golden"].get("forbidden_facts", [])

    context = _format_sources_for_llm(sources, use_compression=len(sources) > 10)
    user_prompt = (
        f"NUTZERANFRAGE:\n{query}\n\n"
        f"KONTEXT AUS DER DATENBANK:\n{context}\n\n"
        f"ANWEISUNG:\n"
        f"1. Beantworte die Frage ausschließlich auf Basis des Kontexts.\n"
        f"2. Bei Ortsfragen: Nenne ALLE unterschiedlichen Städte/Orte aus den Quellen "
        f"(Felder 'Stadtname:', 'Ort:' oder GPS-Koordinaten).\n"
        f"3. Erfinde keine Fakten die nicht im Kontext stehen."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    t0 = time.time()
    try:
        with model_override(provider, model):
            answer = chat(messages)
        latency_ms = int((time.time() - t0) * 1000)
        error = None
    except Exception as exc:
        answer     = ""
        latency_ms = int((time.time() - t0) * 1000)
        error      = str(exc)

    if error:
        return {
            "test_id":   case["test_id"],
            "query":     query,
            "verdict":   "ERROR",
            "score":     0.0,
            "latency_ms": latency_ms,
            "error":     error,
        }

    result = evaluate(
        query=query,
        golden_answer=golden,
        generated_answer=answer,
        method="combined",
        required_facts=required_facts,
        forbidden_facts=forbidden_facts,
    )

    return {
        "test_id":        case["test_id"],
        "query":          query,
        "answer":         answer,
        "golden":         golden,
        "verdict":        result["verdict"],
        "score":          result.get("score", 0.0),
        "embedding_sim":  result.get("embedding_similarity"),
        "missing_facts":  result.get("missing_facts", []),
        "wrong_facts":    result.get("wrong_facts", []),
        "reasoning":      result.get("judge_reasoning", ""),
        "latency_ms":     latency_ms,
    }


def _run_case_thinking(case: dict, provider: str | None, model: str | None,
                       max_iterations: int = 3) -> dict:
    """
    Führt einen Benchmark-Test mit dem Thinking Mode (Researcher → Challenger → Decider) aus.
    Verwendet synchrone Wrapper um die async Thinking-Mode Pipeline.
    """
    import asyncio
    from backend.rag.retriever_v2 import _format_sources_for_llm
    from backend.rag.evaluator import evaluate
    from backend.rag.thinking_mode import thinking_mode_stream
    import json as _json

    query          = case["query"]
    sources        = case["snapshot"].get("sources", [])
    golden         = case["golden"]["answer"]
    required_facts = case["golden"].get("required_facts", [])
    forbidden_facts= case["golden"].get("forbidden_facts", [])

    context = _format_sources_for_llm(sources, use_compression=len(sources) > 10)

    t0 = time.time()
    answer = ""
    dialog_events = []
    error = None

    async def _run_thinking():
        nonlocal answer, dialog_events
        async for event_str in thinking_mode_stream(
            query=query,
            context=context,
            max_iterations=max_iterations,
        ):
            try:
                event = _json.loads(event_str.strip())
                dialog_events.append(event)
                if event.get("type") == "text":
                    answer += event.get("content", "")
            except Exception:
                pass

    try:
        with model_override(provider, model):
            asyncio.run(_run_thinking())
        latency_ms = int((time.time() - t0) * 1000)
    except Exception as exc:
        answer     = ""
        latency_ms = int((time.time() - t0) * 1000)
        error      = str(exc)

    if error:
        return {
            "test_id":     case["test_id"],
            "query":       query,
            "verdict":     "ERROR",
            "score":       0.0,
            "latency_ms":  latency_ms,
            "error":       error,
            "mode":        "thinking",
        }

    result = evaluate(
        query=query,
        golden_answer=golden,
        generated_answer=answer,
        method="combined",
        required_facts=required_facts,
        forbidden_facts=forbidden_facts,
    )

    # Zähle Iterationen aus Dialog-Events
    iterations_done = len([e for e in dialog_events if e.get("type") == "researcher"])

    return {
        "test_id":        case["test_id"],
        "query":          query,
        "answer":         answer,
        "golden":         golden,
        "verdict":        result["verdict"],
        "score":          result.get("score", 0.0),
        "embedding_sim":  result.get("embedding_similarity"),
        "missing_facts":  result.get("missing_facts", []),
        "wrong_facts":    result.get("wrong_facts", []),
        "reasoning":      result.get("judge_reasoning", ""),
        "latency_ms":     latency_ms,
        "mode":           "thinking",
        "iterations":     iterations_done,
        "dialog_events":  len(dialog_events),
    }


def _summarize(results: list[dict], model_label: str) -> dict:
    if not results:
        return {"model": model_label, "tested": 0, "overall_score": 0.0}

    n        = len(results)
    passed   = sum(1 for r in results if r["verdict"] == "PASS")
    partial  = sum(1 for r in results if r["verdict"] == "PARTIAL")
    failed   = sum(1 for r in results if r["verdict"] in ("FAIL", "ERROR"))
    avg_score= sum(r["score"] for r in results) / n
    avg_lat  = sum(r["latency_ms"] for r in results) / n

    return {
        "model":         model_label,
        "tested":        n,
        "pass":          passed,
        "partial":       partial,
        "fail":          failed,
        "pass_rate":     round(passed / n, 3),
        "partial_rate":  round(partial / n, 3),
        "fail_rate":     round(failed / n, 3),
        "overall_score": round(avg_score, 3),
        "avg_latency_ms":round(avg_lat),
        "details":       results,
    }


def _print_table(summaries: list[dict]) -> None:
    print("\n" + "=" * 80)
    print(f"{'RAG BENCHMARK RESULTS':^80}")
    print("=" * 80)
    print(f"{'Model':<30} {'Tests':>5} {'PASS':>6} {'PART':>6} {'FAIL':>6} {'Score':>8} {'Latenz':>10}")
    print("-" * 80)

    summaries_sorted = sorted(summaries, key=lambda s: s["overall_score"], reverse=True)
    for i, s in enumerate(summaries_sorted):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
        print(
            f"{medal} {s['model']:<28} {s['tested']:>5} "
            f"{s['pass']:>6} {s['partial']:>6} {s['fail']:>6} "
            f"{s['overall_score']:>7.3f}  {s['avg_latency_ms']:>8}ms"
        )
    print("=" * 80)
    print("\nScore: 1.0=PASS  0.5=PARTIAL  0.0=FAIL  (gewichteter Durchschnitt)\n")


def run_benchmark(model_specs: list[str], only_case: str | None = None,
                  use_thinking_mode: bool = False) -> None:
    cases = _load_test_cases(only_case)
    if not cases:
        print(f"❌ Keine Test-Cases in {FIXTURES_DIR}")
        print("   → Erst Queries mit golden_answer versehen:")
        print("     POST /api/v1/query-logs/{id}/golden")
        print("   → Dann exportieren:")
        print("     python scripts/export_test_cases.py")
        return

    mode_label = "THINKING MODE" if use_thinking_mode else "STANDARD MODE"
    print(f"📋 {len(cases)} Test-Case(s) geladen  [{mode_label}]")

    # Modell-Specs parsen: "ollama:phi4", "gemini:gemini-2.0-flash" oder nur "phi4"/"qwen3:8b"
    # Bekannte Provider-Namen — alles andere ist Ollama-Modellname (z.B. "qwen3:8b")
    KNOWN_PROVIDERS = {"ollama", "openai", "anthropic", "gemini"}
    parsed_models = []
    for spec in model_specs:
        if ":" in spec:
            prefix, rest = spec.split(":", 1)
            if prefix.lower() in KNOWN_PROVIDERS:
                provider, model = prefix.lower(), rest
            else:
                # Kein bekannter Provider → ganzer String ist Ollama-Modellname (z.B. "qwen3:8b")
                provider, model = None, spec
        else:
            provider, model = None, spec if spec != "default" else None
        label = f"{provider}:{model}" if provider else (model or "config-default")
        if use_thinking_mode:
            label += " [thinking]"
        parsed_models.append((label, provider, model))

    REPORTS_DIR.mkdir(exist_ok=True)
    all_summaries = []

    for label, provider, model in parsed_models:
        print(f"\n🔄 Teste Modell: {label}")
        results = []
        for i, case in enumerate(cases, 1):
            print(f"  [{i}/{len(cases)}] {case['test_id']} – {case['query'][:60]}...")
            if use_thinking_mode:
                r = _run_case_thinking(case, provider, model, max_iterations=3)
            else:
                r = _run_case(case, provider, model)
            verdict_icon = {"PASS": "✅", "PARTIAL": "🟡", "FAIL": "❌", "ERROR": "💥"}.get(r["verdict"], "?")
            extra = f" iter={r.get('iterations', '-')}" if use_thinking_mode else ""
            print(f"         {verdict_icon} {r['verdict']}  score={r['score']:.2f}  {r['latency_ms']}ms{extra}")
            if r.get("wrong_facts"):
                print(f"         wrong: {r['wrong_facts']}")
            if r.get("missing_facts"):
                print(f"         missing: {r['missing_facts']}")
            results.append(r)

        summary = _summarize(results, label)
        all_summaries.append(summary)

    _print_table(all_summaries)

    # Report speichern
    ts = time.strftime("%Y%m%d_%H%M%S")
    suffix = "_thinking" if use_thinking_mode else ""
    report_path = REPORTS_DIR / f"benchmark_{ts}{suffix}.json"
    report = {
        "timestamp":    ts,
        "mode":         "thinking" if use_thinking_mode else "standard",
        "test_cases":   len(cases),
        "models":       len(parsed_models),
        "winner":       max(all_summaries, key=lambda s: s["overall_score"])["model"] if all_summaries else None,
        "summaries":    [{k: v for k, v in s.items() if k != "details"} for s in all_summaries],
        "full_results": all_summaries,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📄 Report gespeichert: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG Benchmark – Modellvergleich")
    parser.add_argument(
        "--models",
        default="default",
        help='Kommagetrennte Modell-Specs: "phi4,qwen3" oder "ollama:phi4,openai:gpt-4o"'
    )
    parser.add_argument(
        "--case",
        default=None,
        help="Nur diesen Test-Case ausführen (query_id)"
    )
    parser.add_argument(
        "--thinking-mode",
        action="store_true",
        default=False,
        help="Verwendet Thinking Mode (Researcher → Challenger → Decider) statt Standard-RAG"
    )
    args = parser.parse_args()
    specs = [m.strip() for m in args.models.split(",") if m.strip()]
    run_benchmark(specs, only_case=args.case, use_thinking_mode=args.thinking_mode)
