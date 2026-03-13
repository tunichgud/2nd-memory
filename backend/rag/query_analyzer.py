"""
query_analyzer.py – LLM-basierte Query-Analyse & Decomposition für RAG v3.

Unterschied zu query_parser.py (v2):
  - query_parser.py: Regelbasiert, schnell, für einfache Queries
  - query_analyzer.py: LLM-basiert, intelligent, für komplexe Queries

Hauptfunktion:
  analyze_query() → Zerlegt komplexe Anfragen in Sub-Queries
  für Chain-of-Thought Reasoning.

Beispiel:
  "Was kann ich Marie zum Geburtstag schenken?"
  → AnalyzedQuery(
      query_type="recommendation",
      complexity="complex",
      sub_queries=[
        "Schritt 1: Finde alle Nachrichten mit Marie",
        "Schritt 2: Finde alle Fotos mit Marie",
        "Schritt 3: Extrahiere Interessen/Hobbies aus Kontext",
        "Schritt 4: Generiere Geschenkideen basierend auf Interessen"
      ],
      temporal_fuzzy=False,
      entities=["Marie"]
    )
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class AnalyzedQuery:
    """Ergebnis der LLM-basierten Query-Analyse."""
    raw: str  # Original-Query
    query_type: str  # "fact_retrieval" | "temporal_inference" | "multi_entity_reasoning" | "recommendation"
    complexity: str  # "simple" | "medium" | "complex"
    sub_queries: list[str] = field(default_factory=list)  # Zerlegte Teilschritte
    temporal_fuzzy: bool = False  # Braucht temporale Fuzzy-Expansion?
    entities: list[str] = field(default_factory=list)  # Extrahierte Personen/Orte
    reasoning: str = ""  # LLM-Begründung (für Debugging)


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

def _get_analyzer_prompt() -> str:
    """System Prompt für Query Analyzer."""
    from backend.llm.prompt_utils import get_current_date_compact, get_year_context

    year_ctx = get_year_context()

    return f"""Du bist ein Query Analyzer für ein persönliches Gedächtnis-System (RAG).

{get_current_date_compact()}

Deine Aufgabe: Analysiere Nutzeranfragen und zerlege komplexe Fragen in Teilschritte.

## Anfrage-Typen

1. **fact_retrieval**: Direkte Fakten-Abfrage
   - Beispiel: "Wo war ich am 15. August 2024?"
   - Strategie: Direkte Suche in Fotos/Messages

2. **temporal_inference**: Zeitbezogene Unschärfe
   - Beispiel: "Wo war ich letzten Sommer?"
   - Strategie: Zeitraum berechnen → Fuzzy-Expansion (±1 Jahr)

3. **multi_entity_reasoning**: Mehrere Entitäten verknüpft
   - Beispiel: "Was habe ich mit Marie in München gemacht?"
   - Strategie: Schritt 1: Finde Datum (München-Aufenthalt) → Schritt 2: Suche Marie-Messages/Fotos in diesem Zeitraum

4. **recommendation**: Empfehlungen ableiten
   - Beispiel: "Was kann ich Marie zum Geburtstag schenken?"
   - Strategie: Schritt 1: Sammle Infos über Marie → Schritt 2: Extrahiere Interessen → Schritt 3: Generiere Ideen

## Komplexität

- **simple**: 1 Schritt (direkte DB-Suche reicht)
- **medium**: 2-3 Schritte (z.B. Datum finden, dann suchen)
- **complex**: 4+ Schritte (Multi-Hop Reasoning nötig)

## Temporal Fuzzy

Setze `temporal_fuzzy: true` wenn:
- Relative Zeitangaben ("letztes Jahr", "damals", "neulich")
- User könnte sich im Jahr geirrt haben
- Ungenaue Zeitangaben ("Sommer 2024" statt "August 2024")

## Sub-Queries

Zerlege komplexe Anfragen in **sequentielle** Schritte.
Jeder Schritt baut auf vorherigen auf (Chain-of-Thought).

Formuliere als **Imperative** (Befehlsform):
- ✅ "Finde alle Fotos in München"
- ❌ "Ich suche Fotos in München"

## Entities

Extrahiere:
- Personennamen (echte Namen, keine Pronomen)
- Ortsnamen (Städte, Regionen, Sehenswürdigkeiten)

## Output-Format

Antworte NUR mit gültigem JSON (kein Markdown, keine Erklärungen):

{{
  "query_type": "fact_retrieval|temporal_inference|multi_entity_reasoning|recommendation",
  "complexity": "simple|medium|complex",
  "sub_queries": ["Schritt 1: ...", "Schritt 2: ...", ...],
  "temporal_fuzzy": true|false,
  "entities": ["Person1", "Ort1", ...],
  "reasoning": "Kurze Begründung für die Zerlegung"
}}

## Beispiele

### Beispiel 1: Simple Query
User: "Wo war ich am 15. August 2024?"
{{
  "query_type": "fact_retrieval",
  "complexity": "simple",
  "sub_queries": ["Finde Fotos vom 15. August 2024"],
  "temporal_fuzzy": false,
  "entities": [],
  "reasoning": "Konkretes Datum gegeben, direkte Suche möglich"
}}

### Beispiel 2: Temporal Inference
User: "Wo war ich letzten Sommer?"
{{
  "query_type": "temporal_inference",
  "complexity": "medium",
  "sub_queries": [
    "Berechne Zeitraum für 'letzten Sommer' ({year_ctx['last_year']}-06-01 bis {year_ctx['last_year']}-08-31)",
    "Finde alle Fotos in diesem Zeitraum",
    "Gruppiere Fotos nach Orten (GPS-Cluster)"
  ],
  "temporal_fuzzy": true,
  "entities": [],
  "reasoning": "User könnte auch Sommer {year_ctx['last_year'] - 1} meinen, daher fuzzy=true"
}}

### Beispiel 3: Multi-Entity Reasoning
User: "Was habe ich mit Marie in München gemacht?"
{{
  "query_type": "multi_entity_reasoning",
  "complexity": "medium",
  "sub_queries": [
    "Finde Zeitraum des München-Aufenthalts via Fotos",
    "Suche Nachrichten mit Marie in diesem Zeitraum",
    "Suche Fotos mit Marie in München"
  ],
  "temporal_fuzzy": false,
  "entities": ["Marie", "München"],
  "reasoning": "Datum unbekannt → erst Fotos suchen, dann Messages filtern"
}}

### Beispiel 4: Recommendation
User: "Was kann ich Marie zum Geburtstag schenken?"
{{
  "query_type": "recommendation",
  "complexity": "complex",
  "sub_queries": [
    "Finde alle Nachrichten mit Marie",
    "Finde alle Fotos mit Marie",
    "Extrahiere Maries Interessen und Hobbies aus Nachrichten und Foto-Beschreibungen",
    "Generiere Geschenkideen basierend auf den gefundenen Interessen"
  ],
  "temporal_fuzzy": false,
  "entities": ["Marie"],
  "reasoning": "Multi-Hop: Infos sammeln → Interessen ableiten → Empfehlungen generieren"
}}

Analysiere jetzt die folgende Anfrage:
"""


# ---------------------------------------------------------------------------
# Query Analysis
# ---------------------------------------------------------------------------

def analyze_query(query: str, use_fallback: bool = True) -> AnalyzedQuery:
    """
    Analysiert eine Nutzeranfrage und zerlegt sie in Sub-Queries.

    Args:
        query: Die Nutzeranfrage
        use_fallback: Wenn True, nutze regelbasierten Fallback bei LLM-Fehler

    Returns:
        AnalyzedQuery mit Typ, Komplexität, Sub-Queries, etc.

    Raises:
        ValueError: Wenn LLM-Antwort ungültig und kein Fallback verfügbar
    """
    from backend.llm.connector import chat

    logger.info("Analysiere Query: '%s'", query[:100])

    # LLM-basierte Analyse
    try:
        messages = [
            {"role": "system", "content": _get_analyzer_prompt()},
            {"role": "user", "content": query}
        ]

        raw_response = chat(messages)
        logger.debug("LLM Response (raw): %s", raw_response[:200])

        # JSON extrahieren (auch wenn Markdown drumherum ist)
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if not json_match:
            raise ValueError(f"Kein JSON in LLM-Antwort: {raw_response[:200]}")

        data = json.loads(json_match.group())

        # Validierung
        if "query_type" not in data or "complexity" not in data:
            raise ValueError(f"Unvollständige Antwort: {data}")

        result = AnalyzedQuery(
            raw=query,
            query_type=data["query_type"],
            complexity=data["complexity"],
            sub_queries=data.get("sub_queries", []),
            temporal_fuzzy=data.get("temporal_fuzzy", False),
            entities=data.get("entities", []),
            reasoning=data.get("reasoning", "")
        )

        logger.info(
            "Query analysiert: type=%s, complexity=%s, sub_queries=%d, temporal_fuzzy=%s",
            result.query_type, result.complexity, len(result.sub_queries), result.temporal_fuzzy
        )

        return result

    except Exception as exc:
        logger.warning("LLM Query-Analyse fehlgeschlagen: %s", exc)

        if not use_fallback:
            raise

        # Fallback: Regelbasierte Analyse
        logger.info("Nutze regelbasierten Fallback")
        return _analyze_query_fallback(query)


def _analyze_query_fallback(query: str) -> AnalyzedQuery:
    """
    Regelbasierter Fallback wenn LLM-Analyse fehlschlägt.

    Einfache Heuristiken basierend auf Keywords.
    """
    q_lower = query.lower()

    # Temporal Keywords
    temporal_keywords = ["letztes jahr", "letzten sommer", "damals", "neulich", "vor kurzem"]
    is_temporal = any(kw in q_lower for kw in temporal_keywords)

    # Recommendation Keywords
    recommendation_keywords = ["schenken", "empfehlung", "vorschlag", "idee", "was kann ich"]
    is_recommendation = any(kw in q_lower for kw in recommendation_keywords)

    # Entity-Extraktion (sehr simpel)
    # Echte Personennamen sind meist Großgeschrieben
    words = query.split()
    entities = [w for w in words if w[0].isupper() and len(w) > 2 and w not in ["Wo", "Was", "Wann", "Wie"]]

    # Bestimme Typ
    if is_recommendation:
        query_type = "recommendation"
        complexity = "complex"
        sub_queries = [
            f"Finde Informationen über {entities[0] if entities else 'die Person'}",
            "Extrahiere Interessen aus Kontext",
            "Generiere Empfehlungen"
        ]
    elif is_temporal:
        query_type = "temporal_inference"
        complexity = "medium"
        sub_queries = [
            "Berechne Zeitraum",
            "Suche in Fotos und Nachrichten"
        ]
    elif len(entities) > 1:
        query_type = "multi_entity_reasoning"
        complexity = "medium"
        sub_queries = [
            f"Suche nach {entities[0]}",
            f"Filtere nach {entities[1]}"
        ]
    else:
        query_type = "fact_retrieval"
        complexity = "simple"
        sub_queries = ["Suche in Datenbank"]

    return AnalyzedQuery(
        raw=query,
        query_type=query_type,
        complexity=complexity,
        sub_queries=sub_queries,
        temporal_fuzzy=is_temporal,
        entities=entities,
        reasoning="Regelbasierter Fallback (LLM nicht verfügbar)"
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def should_use_chain_of_thought(analyzed: AnalyzedQuery) -> bool:
    """
    Entscheidet ob Chain-of-Thought nötig ist.

    Returns:
        True wenn komplexe Query (medium/complex) ODER >2 Sub-Queries
    """
    return (
        analyzed.complexity in ("medium", "complex") or
        len(analyzed.sub_queries) > 2
    )


def format_sub_queries_for_logging(analyzed: AnalyzedQuery) -> str:
    """Formatiert Sub-Queries für Log-Ausgabe."""
    if not analyzed.sub_queries:
        return "(keine Sub-Queries)"

    lines = [f"  {i+1}. {sq}" for i, sq in enumerate(analyzed.sub_queries)]
    return "\n".join(lines)
