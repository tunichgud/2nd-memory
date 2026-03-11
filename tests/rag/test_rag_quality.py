"""
test_rag_quality.py – Parametrisierte RAG-Quality-Tests.

Jeder Test-Case aus tests/fixtures/rag_test_cases/ wird als eigenständiger
pytest-Test ausgeführt. Die Tests sind hermetic: sie nutzen den gespeicherten
Source-Snapshot statt live ChromaDB abzufragen.

Ausführung:
  # Mit Standard-Modell aus config.yaml:
  pytest tests/rag/ -v

  # Mit explizitem Modell:
  pytest tests/rag/ -v --model phi4 --provider ollama
  pytest tests/rag/ -v --model gpt-4o --provider openai
  pytest tests/rag/ -v --model gemini-2.0-flash --provider gemini

Score-Bedeutung:
  1.0  = PASS    (alle Fakten korrekt)
  0.5  = PARTIAL (teilweise korrekt)
  0.0  = FAIL    (falsche Fakten oder halluziniert)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.rag.conftest import model_override


# ---------------------------------------------------------------------------
# Test-Case Loader (pytest parametrize)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "rag_test_cases"


def _load_cases() -> list[tuple[str, dict]]:
    """Gibt Liste von (test_id, case_dict) zurück für pytest.mark.parametrize."""
    if not FIXTURES_DIR.exists():
        return []
    cases = []
    for f in sorted(FIXTURES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cases.append((data["test_id"], data))
        except Exception:
            pass
    return cases


_CASES = _load_cases()
_IDS = [c[0] for c in _CASES]


def pytest_generate_tests(metafunc):
    """Dynamische Parametrisierung: ein Test pro JSON-File."""
    if "test_case" in metafunc.fixturenames:
        metafunc.parametrize("test_case", [c[1] for c in _CASES], ids=_IDS)


# ---------------------------------------------------------------------------
# Hilfs-Funktion: hermetic LLM-Call
# ---------------------------------------------------------------------------

def _run_hermetic(query: str, sources: list[dict], system_prompt: str, model: str | None, provider: str | None) -> tuple[str, float]:
    """Führt LLM-Call mit Snapshot-Sources aus. Gibt (answer, latency_ms) zurück."""
    from backend.rag.retriever_v2 import _format_sources_for_llm, _get_system_prompt
    from backend.llm.connector import chat

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
    # Nutze aktuellen System-Prompt statt dem gespeicherten Snapshot
    messages = [
        {"role": "system", "content": _get_system_prompt()},
        {"role": "user", "content": user_prompt},
    ]

    t0 = time.time()
    with model_override(provider, model):
        answer = chat(messages)
    latency_ms = (time.time() - t0) * 1000
    return answer, latency_ms


# ---------------------------------------------------------------------------
# Der eigentliche Test
# ---------------------------------------------------------------------------

@pytest.mark.rag_quality
def test_rag_answer_quality(test_case: dict, rag_model, rag_provider):
    """
    Hermetic RAG-Quality-Test: injiziert Source-Snapshot, ruft LLM auf,
    evaluiert Antwort gegen golden_answer.

    PASS    bei score >= 0.7
    PARTIAL bei score >= 0.4
    FAIL    bei score < 0.4
    """
    from backend.rag.evaluator import evaluate

    query        = test_case["query"]
    snapshot     = test_case["snapshot"]
    golden_data  = test_case["golden"]

    golden_answer   = golden_data["answer"]
    required_facts  = golden_data.get("required_facts", [])
    forbidden_facts = golden_data.get("forbidden_facts", [])
    sources         = snapshot.get("sources", [])
    system_prompt   = snapshot.get("system_prompt", "")

    # Hermetic LLM-Call
    answer, latency_ms = _run_hermetic(query, sources, system_prompt, rag_model, rag_provider)

    # Semantische Evaluation
    result = evaluate(
        query=query,
        golden_answer=golden_answer,
        generated_answer=answer,
        method="combined",
        required_facts=required_facts,
        forbidden_facts=forbidden_facts,
    )

    verdict  = result["verdict"]
    score    = result.get("score", 0.0)
    missing  = result.get("missing_facts", [])
    wrong    = result.get("wrong_facts", [])
    reasoning = result.get("judge_reasoning", "")

    # Ausgabe für pytest -v
    print(f"\n{'='*60}")
    print(f"Query:    {query}")
    print(f"Golden:   {golden_answer}")
    print(f"Answer:   {answer[:200]}{'...' if len(answer) > 200 else ''}")
    print(f"Verdict:  {verdict}  Score: {score:.2f}  Latenz: {latency_ms:.0f}ms")
    if missing:
        print(f"Missing:  {missing}")
    if wrong:
        print(f"Wrong:    {wrong}")
    if reasoning:
        print(f"Reason:   {reasoning}")
    print(f"{'='*60}")

    # Test schlägt fehl wenn Score unter 0.4
    assert score >= 0.4, (
        f"RAG-Qualität zu niedrig (score={score:.2f}, verdict={verdict})\n"
        f"Query: {query}\n"
        f"Missing facts: {missing}\n"
        f"Wrong facts:   {wrong}\n"
        f"Reason: {reasoning}"
    )
