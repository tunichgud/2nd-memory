"""
Tests für context_manager.py – Context Window Management
"""

import pytest
from backend.rag.context_manager import (
    count_tokens,
    compress_text,
    compress_sources,
    CompressionMode,
    ContextBudget,
    ProgressiveContext,
)


def test_count_tokens_basic():
    """Test token counting mit verschiedenen Texten."""
    # Kurzer Text
    assert count_tokens("Hello World") > 0
    # Langer Text sollte mehr Tokens haben
    short = "Hello"
    long = "Hello " * 100
    assert count_tokens(long) > count_tokens(short) * 50


def test_compress_text_full_mode():
    """Test FULL mode (nur truncate wenn nötig)."""
    text = "Dies ist ein kurzer Text."
    result = compress_text(text, max_tokens=100, mode=CompressionMode.FULL)
    assert result == text  # Sollte unverändert sein


def test_compress_text_compact_mode():
    """Test COMPACT mode (Kernsätze)."""
    text = "Erster Satz. Zweiter Satz. Dritter Satz. Vierter Satz. Fünfter Satz. Letzter Satz."
    result = compress_text(text, max_tokens=20, mode=CompressionMode.COMPACT)
    # Sollte erste 2 + letzter Satz enthalten
    assert "Erster Satz" in result
    assert "Zweiter Satz" in result
    assert "Letzter Satz" in result
    assert "Vierter Satz" not in result


def test_compress_text_minimal_mode():
    """Test MINIMAL mode (nur erster Satz)."""
    text = "Erster Satz. Zweiter Satz. Dritter Satz."
    result = compress_text(text, max_tokens=10, mode=CompressionMode.MINIMAL)
    assert "Erster Satz" in result
    assert "Zweiter Satz" not in result


def test_compress_sources_empty():
    """Test mit leerer Source-Liste."""
    result = compress_sources([], budget=ContextBudget())
    assert "Keine passenden Einträge" in result


def test_compress_sources_basic():
    """Test mit echten Sources."""
    sources = [
        {
            "id": "photo_1",
            "collection": "photos",
            "score": 0.95,
            "document": "Eine Gruppe von Personen steht am Strand und lacht. Die Sonne geht unter.",
            "metadata": {
                "date_iso": "2024-08-15T14:30:00",
                "cluster": "Ostsee-Strand",
                "lat": 54.123,
                "lon": 13.456
            }
        },
        {
            "id": "photo_2",
            "collection": "photos",
            "score": 0.85,
            "document": "Ein Foto von einem Restaurant mit mediterranem Essen.",
            "metadata": {
                "date_iso": "2024-08-16T19:00:00",
                "place_name": "Taverna Greca"
            }
        },
        {
            "id": "message_1",
            "collection": "messages",
            "score": 0.75,
            "document": "Hey, wollen wir morgen ins Kino gehen? Ich habe gehört der neue Film ist super!",
            "metadata": {
                "date_iso": "2024-08-17T10:15:00"
            }
        }
    ]

    budget = ContextBudget(max_tokens=2000)
    result = compress_sources(sources, budget=budget, top_n_full=2)

    # Check: Alle Sources sollten enthalten sein
    assert "[1 – 📷 FOTO" in result
    assert "[2 – 📷 FOTO" in result
    assert "[3 – 💬 NACHRICHT" in result

    # Check: Top-2 sollten vollen Text haben
    assert "Eine Gruppe von Personen steht am Strand" in result
    assert "Restaurant mit mediterranem Essen" in result

    # Check: Metadaten sollten enthalten sein
    assert "2024-08-15" in result
    assert "Ostsee-Strand" in result
    assert "54.123°N" in result


def test_compress_sources_budget_limit():
    """Test dass Budget-Limit respektiert wird."""
    # Erstelle viele Sources (50 Stück)
    sources = []
    for i in range(50):
        sources.append({
            "id": f"photo_{i}",
            "collection": "photos",
            "score": 0.9 - (i * 0.01),  # Absteigend
            "document": f"Dies ist Foto Nummer {i}. " * 50,  # Langer Text
            "metadata": {"date_iso": f"2024-08-{i+1:02d}T12:00:00"}
        })

    # Sehr kleines Budget
    budget = ContextBudget(max_tokens=500)
    result = compress_sources(sources, budget=budget, top_n_full=3)

    # Check: Sollte deutlich weniger als 50 Sources enthalten
    assert result.count("[") < 20  # Weniger als 20 Quellen


def test_compress_sources_ranking():
    """Test dass Sources nach Score sortiert werden."""
    sources = [
        {
            "id": "low_score",
            "collection": "photos",
            "score": 0.3,
            "document": "Niedrige Relevanz",
            "metadata": {}
        },
        {
            "id": "high_score",
            "collection": "photos",
            "score": 0.95,
            "document": "Hohe Relevanz",
            "metadata": {}
        },
        {
            "id": "medium_score",
            "collection": "photos",
            "score": 0.6,
            "document": "Mittlere Relevanz",
            "metadata": {}
        }
    ]

    result = compress_sources(sources, top_n_full=1)

    # Check: Highest score sollte zuerst kommen
    assert result.index("Hohe Relevanz") < result.index("Mittlere Relevanz")
    assert result.index("Mittlere Relevanz") < result.index("Niedrige Relevanz")


def test_progressive_context_basic():
    """Test ProgressiveContext für Chain-of-Thought."""
    pc = ProgressiveContext()

    # Schritt 1: Initiale Quellen
    sources_1 = [
        {
            "id": "photo_1",
            "collection": "photos",
            "score": 0.9,
            "document": "Erste Information",
            "metadata": {}
        }
    ]
    context_1 = pc.add_sources(sources_1, "Schritt 1: Fotos suchen")
    assert "Erste Information" in context_1
    assert len(pc.all_sources) == 1

    # Schritt 2: Neue Quellen
    sources_2 = [
        {
            "id": "photo_1",  # Duplikat
            "collection": "photos",
            "score": 0.9,
            "document": "Erste Information",
            "metadata": {}
        },
        {
            "id": "message_1",  # NEU
            "collection": "messages",
            "score": 0.8,
            "document": "Zweite Information",
            "metadata": {}
        }
    ]
    context_2 = pc.add_sources(sources_2, "Schritt 2: Messages suchen")
    assert "Zweite Information" in context_2
    assert len(pc.all_sources) == 2  # Nur 2 (Duplikat ignoriert)


def test_progressive_context_with_summaries():
    """Test Progressive Context mit Step-Summaries."""
    pc = ProgressiveContext()

    sources = [{"id": "1", "collection": "photos", "score": 0.9, "document": "Test", "metadata": {}}]
    pc.add_sources(sources, "Schritt 1")

    # Füge Summary hinzu
    pc.add_step_summary("Erkenntnisse aus Schritt 1: User war in München")

    # Nächster Schritt sollte Summary referenzieren
    context_2 = pc.add_sources([], "Schritt 2")
    assert "BISHERIGE ERKENNTNISSE" in context_2
    assert "München" in context_2


def test_context_budget_calculation():
    """Test ContextBudget Berechnungen."""
    budget = ContextBudget(max_tokens=10000, system_prompt_tokens=500, user_prompt_base_tokens=200)
    assert budget.available_for_sources == 9300  # 10000 - 500 - 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
