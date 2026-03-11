"""
conftest.py – pytest-Konfiguration für RAG-Quality-Tests.

Fügt CLI-Optionen hinzu:
  --model    LLM-Modell für den Test  (z.B. phi4, qwen3, gpt-4o)
  --provider LLM-Provider             (z.B. ollama, openai, anthropic, gemini)
  --cases    Pfad zu Test-Case-Verzeichnis (default: tests/fixtures/rag_test_cases)

Beispiel:
  pytest tests/rag/ -v
  pytest tests/rag/ -v --model phi4 --provider ollama
  pytest tests/rag/ -v --model gpt-4o --provider openai
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pytest


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "rag_test_cases"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--model",    action="store", default=None,  help="LLM-Modell (z.B. phi4, qwen3, gpt-4o)")
    parser.addoption("--provider", action="store", default=None,  help="LLM-Provider (ollama, openai, anthropic, gemini)")
    parser.addoption("--cases",    action="store", default=str(FIXTURES_DIR), help="Pfad zu Test-Cases")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "rag_quality: RAG-Quality-Tests mit echten LLM-Calls")


@pytest.fixture(scope="session")
def rag_model(request: pytest.FixtureRequest) -> str | None:
    return request.config.getoption("--model")


@pytest.fixture(scope="session")
def rag_provider(request: pytest.FixtureRequest) -> str | None:
    return request.config.getoption("--provider")


@pytest.fixture(scope="session")
def test_cases_dir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.getoption("--cases"))


@pytest.fixture(scope="session")
def all_test_cases(test_cases_dir: Path) -> list[dict]:
    """Lädt alle JSON-Test-Cases aus dem Fixtures-Verzeichnis."""
    cases = []
    if test_cases_dir.exists():
        for f in sorted(test_cases_dir.glob("*.json")):
            try:
                cases.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception as e:
                pytest.warns(UserWarning, match=str(f))
    return cases


@contextmanager
def model_override(provider: str | None, model: str | None) -> Generator:
    """Context-Manager: überschreibt temporär den LLM-Provider/Modell in der Config."""
    if not provider and not model:
        yield
        return

    import backend.llm.connector as conn
    original = conn._cfg
    if original is None:
        conn.get_cfg()  # initialisieren
        original = conn._cfg

    import copy
    patched = copy.deepcopy(original)
    if provider:
        patched["llm"]["provider"] = provider
    if model:
        patched["llm"]["model"] = model

    conn._cfg = patched
    try:
        yield
    finally:
        conn._cfg = original


@pytest.fixture(scope="session")
def model_ctx(rag_provider, rag_model):
    """Gibt den model_override Context-Manager für die Session zurück."""
    return lambda: model_override(rag_provider, rag_model)
