# Baseline v1 — Pre Thinking-Mode

**Eingefroren am:** 2026-03-11
**Zweck:** Referenzpunkt vor Einführung des Thinking-Mode (Researcher → Challenger → Decider)

---

## Datei

`reports/baseline_v1_pre_thinking_mode.json`
Kopie von: `reports/benchmark_20260311_180553.json`

---

## Ergebnis-Zusammenfassung

| Modell | Tests | PASS | PARTIAL | FAIL | Score | Ø Latenz |
|--------|-------|------|---------|------|-------|----------|
| phi4 (Ollama) | 3 | 2 | 0 | 1 | **0.633** | 6563 ms |
| gemini-2.5-flash | 3 | 2 | 0 | 1 | **0.633** | 2332 ms |
| gemini-3-flash-preview | 3 | 2 | 0 | 1 | **0.633** | 6365 ms |

Alle drei Modelle erreichen denselben Score — das FAIL-Ergebnis (Max-Treffpunkt) ist strukturell: Die relevante Nachricht war schlicht nicht in den Top-Retrieval-Ergebnissen enthalten.

---

## Test-Cases (v1 — 3 Queries)

| ID | Query | Typ | Ergebnis |
|----|-------|-----|---------|
| `q_20260311_150705_0170df` | Wo treffe ich mich heute mit Max? | Zeitlich + Person | ❌ FAIL |
| `q_20260311_151849_8bf1fb` | Wo war ich mit Anna im letzten August? | Temporal + Person + Foto | ✅ PASS |
| `q_20260311_151907_f749db` | Wo war ich mit Anna im letzten Sommer? | Temporal fuzzy + Person + Foto | ✅ PASS |

---

## Architektur-Stand

- **Retriever:** `retriever_v2.py` (token-aware, ChromaDB, user-id-gefiltert)
- **Streaming:** `retriever_v3_stream.py` mit Thinking-Timeline (query_analysis → thought → tool_call → tool_result)
- **Evaluator:** `evaluator.py` mit combined-Methode (embedding_similarity + LLM-Judge + required_facts)
- **Collections:** photos (500), messages (3659), saved_places (210), reviews (47)
- **Personen auf Fotos:** Anna (241), Marie (86), Alex/Alex (42+56), Monika (16), Frieda (5), Max (1), ...

---

## Bekannte Schwäche (strukturell)

Der Max-Treffpunkt-Test schlägt fehl, weil:
1. Die Nachricht mit dem Treffpunkt ("Villa Romana, Ahrensburg, 12:15") nicht in ChromaDB ist — das Retrieval liefert nur die eigenen Fragen zurück
2. Der Golden Answer beschreibt eine Information, die in den Snapshot-Sources nicht vorhanden war

→ Dies ist kein Modell-Problem, sondern ein Daten-Vollständigkeits-Problem.
→ Die neuen Cross-Domain-Queries (v2, 20 Stück) werden so konstruiert, dass die Antwort tatsächlich in den Daten vorhanden ist.

---

## Nächste Schritte

1. **Cross-Domain Query Suite v2** — 20 neue Queries über mehrere Collections hinweg
2. **Baseline v2** — Benchmark dieser 20 Queries ohne Thinking-Mode
3. **Thinking-Mode** — Branch `feature/thinking-mode`, dann Benchmark v3
4. **Vergleich** v2 vs. v3 = Nachweis ob Thinking-Mode messbar besser ist

---

## Methodik (Evaluator)

```
Score = kombiniert aus:
  1. Embedding-Similarity (Sentence-BERT)
  2. LLM-Judge (strukturiertes Reasoning über Pflicht-Fakten)
  3. Required Facts Check (must_contain)
  4. Forbidden Facts Check (must_not_contain)

PASS    = Score ≥ 0.8
PARTIAL = Score 0.3–0.8
FAIL    = Score < 0.3 oder required_fact fehlt
```
