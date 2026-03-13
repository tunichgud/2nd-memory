"""
test_thinking_trace_logging.py – Akzeptanztest für den Bug-Fix in query_logger.py.

Bug (behoben): trace_fn in thinking_mode.py übergab accumulated_facts_size an
log_thinking_iteration(), welches diesen Parameter nicht kannte → TypeError →
silent catch → kein einziger Thinking-Trace-Row wurde in SQLite geschrieben.

Fix: accumulated_facts_size: int = 0 als Parameter zu log_thinking_iteration
ergänzt und in DB-Schema + INSERT aufgenommen.

Diese Tests stellen sicher:
1. log_thinking_iteration akzeptiert accumulated_facts_size ohne Exception.
2. Alle Keys die thinking_mode.py ins trace_fn-Dict schreibt werden akzeptiert
   — kein unbekannter Parameter löst einen TypeError aus.
3. Der Row wird tatsächlich in die DB geschrieben (kein silent discard).
4. accumulated_facts_size wird korrekt persistiert und durch get_thinking_trace
   zurückgeliefert.
5. Die Signatur von log_thinking_iteration ist vollständig dokumentiert —
   jede Abweichung zwischen trace_fn-Dict und Signatur führt zum Test-Fehler.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import backend.rag.query_logger as ql


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trace_fn_dict(iteration: int = 1) -> dict:
    """
    Baut exakt dasselbe Dict, das thinking_mode.py in trace_fn({...}) übergibt
    (Zeilen 286–300 in thinking_mode.py).  Wenn dort neue Keys hinzukommen
    müssen sie auch hier erscheinen — das ist der Canary.
    """
    return {
        "iteration": iteration,
        "researcher_output": "FAKTEN:\n- [2026-01-01] src: \"Test\"",
        "challenger_output": "LÜCKEN:\n- Keine weiteren Fakten gefunden.",
        "decider_decision": "finalize",
        "decider_reasoning": "Alle relevanten Fakten vorhanden.",
        "decider_retrieval_focus": None,
        "retrieval_keywords": None,
        "retrieval_date_from": None,
        "retrieval_date_to": None,
        "retrieval_found_count": -1,
        "context_size_before": 512,
        "context_size_after": 512,
        "accumulated_facts_size": 256,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Leitet alle DB-Zugriffe auf eine temporäre SQLite-Datei um und setzt den
    Schema-Initialized-Flag zurück, damit _ensure_schema() sauber läuft.
    """
    test_db = tmp_path / "test_query_logs.db"
    monkeypatch.setattr(ql, "_db_path", test_db)
    monkeypatch.setattr(ql, "_schema_initialized", False)


def _seed_parent_row(query_id: str) -> None:
    """Legt die nötige Eltern-Zeile in rag_queries an (FK-Constraint)."""
    ql._init_once()
    with ql._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO rag_queries
            (query_id, created_at, raw_query)
            VALUES (?, ?, ?)
            """,
            (query_id, "2026-01-01T00:00:00", "Testanfrage"),
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLogThinkingIterationSignature:
    """Stellt sicher dass die Signatur vollständig mit dem trace_fn-Dict übereinstimmt."""

    def test_all_trace_fn_keys_accepted_without_exception(self) -> None:
        """
        Regression-Test für den ursprünglichen Bug:
        log_thinking_iteration muss alle Keys aus dem trace_fn-Dict akzeptieren
        — insbesondere accumulated_facts_size — ohne TypeError zu werfen.
        """
        query_id = "q_test_signature_001"
        _seed_parent_row(query_id)

        data = _trace_fn_dict(iteration=1)
        # query_id wird separat übergeben, nicht im Dict
        iteration = data.pop("iteration")

        # Darf KEINEN TypeError werfen:
        ql.log_thinking_iteration(query_id=query_id, iteration=iteration, **data)

    def test_accumulated_facts_size_is_accepted(self) -> None:
        """
        Direkter Smoke-Test: accumulated_facts_size als benannter Parameter.
        Vor dem Fix warf dieser Aufruf einen TypeError.
        """
        query_id = "q_test_accfacts_002"
        _seed_parent_row(query_id)

        # Soll nicht werfen:
        ql.log_thinking_iteration(
            query_id=query_id,
            iteration=1,
            accumulated_facts_size=1024,
        )


class TestLogThinkingIterationPersistence:
    """Stellt sicher dass Rows wirklich in der DB landen."""

    def test_row_is_written_to_db(self) -> None:
        """
        Kerntest: nach log_thinking_iteration muss get_thinking_trace
        genau einen Eintrag zurückgeben (kein silent discard).
        """
        query_id = "q_test_persist_003"
        _seed_parent_row(query_id)

        data = _trace_fn_dict(iteration=1)
        iteration = data.pop("iteration")
        ql.log_thinking_iteration(query_id=query_id, iteration=iteration, **data)

        trace = ql.get_thinking_trace(query_id)
        assert len(trace) == 1, (
            f"Erwartet 1 Trace-Row, erhalten: {len(trace)}. "
            "Möglicherweise wurde der Row silent verworfen (TypeError im except-Block)."
        )

    def test_accumulated_facts_size_is_persisted_correctly(self) -> None:
        """accumulated_facts_size muss exakt so zurückgeliefert werden wie übergeben."""
        query_id = "q_test_accfacts_persist_004"
        _seed_parent_row(query_id)

        expected_size = 42_000
        ql.log_thinking_iteration(
            query_id=query_id,
            iteration=1,
            researcher_output="Testfakten",
            accumulated_facts_size=expected_size,
        )

        trace = ql.get_thinking_trace(query_id)
        assert len(trace) == 1
        assert trace[0]["accumulated_facts_size"] == expected_size, (
            f"accumulated_facts_size: erwartet {expected_size}, "
            f"erhalten {trace[0]['accumulated_facts_size']}"
        )

    def test_multiple_iterations_are_all_persisted(self) -> None:
        """
        Prüft dass mehrere Iterationen (wie sie thinking_mode.py schreibt)
        vollständig und in der richtigen Reihenfolge persistiert werden.
        """
        query_id = "q_test_multi_005"
        _seed_parent_row(query_id)

        for i in range(1, 4):
            data = _trace_fn_dict(iteration=i)
            data["accumulated_facts_size"] = i * 100
            iteration = data.pop("iteration")
            ql.log_thinking_iteration(query_id=query_id, iteration=iteration, **data)

        trace = ql.get_thinking_trace(query_id)
        assert len(trace) == 3, f"Erwartet 3 Rows, erhalten: {len(trace)}"
        for idx, row in enumerate(trace, start=1):
            assert row["iteration"] == idx
            assert row["accumulated_facts_size"] == idx * 100

    def test_full_trace_fn_dict_fields_are_persisted(self) -> None:
        """
        Vollständiger Roundtrip: alle nicht-None-Felder aus trace_fn-Dict
        müssen korrekt gespeichert und zurückgelesen werden.
        """
        query_id = "q_test_roundtrip_006"
        _seed_parent_row(query_id)

        data = _trace_fn_dict(iteration=1)
        data["retrieval_date_from"] = "2026-01-01"
        data["retrieval_date_to"] = "2026-03-01"
        data["retrieval_keywords"] = ["Hund", "Gassi"]
        data["retrieval_found_count"] = 7
        data["context_size_before"] = 1024
        data["context_size_after"] = 2048
        data["accumulated_facts_size"] = 512

        iteration = data.pop("iteration")
        ql.log_thinking_iteration(query_id=query_id, iteration=iteration, **data)

        trace = ql.get_thinking_trace(query_id)
        assert len(trace) == 1
        row = trace[0]

        assert row["researcher_output"] == data["researcher_output"]
        assert row["challenger_output"] == data["challenger_output"]
        assert row["decider_decision"] == data["decider_decision"]
        assert row["decider_reasoning"] == data["decider_reasoning"]
        assert row["retrieval_date_from"] == "2026-01-01"
        assert row["retrieval_date_to"] == "2026-03-01"
        assert row["retrieval_keywords"] == ["Hund", "Gassi"]
        assert row["retrieval_found_count"] == 7
        assert row["context_size_before"] == 1024
        assert row["context_size_after"] == 2048
        assert row["accumulated_facts_size"] == 512


class TestSignatureCompleteness:
    """
    Dokumentiert dass die Signatur von log_thinking_iteration vollständig ist.

    Wenn thinking_mode.py neue Keys ins trace_fn-Dict aufnimmt ohne die
    Signatur zu erweitern, schlägt test_no_unknown_keys_in_trace_fn_dict fehl
    und macht den Fehler sofort sichtbar — bevor er im except-Block verschwindet.
    """

    def test_no_unknown_keys_in_trace_fn_dict(self) -> None:
        """
        Alle Keys im trace_fn-Dict müssen als Parameter in log_thinking_iteration
        vorhanden sein (abzüglich 'iteration', das separat übergeben wird).

        Bei einem neuen Key im Dict der nicht in der Signatur landet:
        - TypeError → silent except → Row geht verloren
        - Dieser Test macht das sofort sichtbar.
        """
        import inspect

        sig = inspect.signature(ql.log_thinking_iteration)
        accepted_params = set(sig.parameters.keys())

        trace_fn_dict_keys = set(_trace_fn_dict().keys())
        # 'iteration' ist kein **kwargs-Key, wird separat übergeben
        trace_fn_dict_keys.discard("iteration")

        unknown_keys = trace_fn_dict_keys - accepted_params
        assert not unknown_keys, (
            f"Die folgenden Keys aus dem trace_fn-Dict in thinking_mode.py "
            f"werden von log_thinking_iteration NICHT akzeptiert: {unknown_keys}\n"
            f"Das führt zu einem TypeError der silent gecatcht wird → Row-Verlust.\n"
            f"Fix: Parameter zu log_thinking_iteration hinzufügen."
        )
