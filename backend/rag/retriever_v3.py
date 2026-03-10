"""
retriever_v3.py – Advanced RAG with Chain-of-Thought, Query Decomposition & Fuzzy Logic.

Neue Features gegenüber v2:
  1. Query Decomposition → Multi-Step Reasoning
  2. Temporal Fuzzy Logic → Toleriert User-Fehler bei Zeitangaben
  3. Synonym-Expansion → "Kneipe" findet auch "Bar", "Pub"
  4. Multi-Shot Retrieval → Probiert mehrere Strategien parallel
  5. Progressive Context Loading → Vermeidet Token-Overflow bei Chain-of-Thought

Architektur:
  User Query
    ↓
  [Query Analyzer] → Zerlegt in Sub-Queries
    ↓
  [Multi-Shot Retrieval] → Fuzzy Temporal + Synonym Expansion
    ↓
  [Progressive Context Manager] → Token-optimiert
    ↓
  [Chain-of-Thought LLM] → Schritt-für-Schritt Reasoning
    ↓
  Final Answer
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.rag.query_analyzer import analyze_query, should_use_chain_of_thought, AnalyzedQuery
from backend.rag.temporal_utils import expand_temporal_query, TemporalRange
from backend.rag.context_manager import compress_sources, ContextBudget, ProgressiveContext
from backend.rag.embedder import embed_single
from backend.rag.store_v2 import query_collection_v2
from backend.rag.store import SEARCHABLE_COLLECTIONS

logger = logging.getLogger(__name__)

_RELEVANT_MIN_SCORE = 0.20
_FALLBACK_MIN_SCORE = 0.42


# ---------------------------------------------------------------------------
# Synonym Expansion
# ---------------------------------------------------------------------------

def expand_query_with_synonyms(query: str, max_variants: int = 3) -> list[str]:
    """
    Erweitert Query mit Synonymen für bessere Recall.

    Beispiel:
        "Kneipe in Brandenburg"
        → ["Kneipe in Brandenburg", "Bar in Brandenburg", "Pub in Brandenburg"]

    Args:
        query: Original-Query
        max_variants: Maximale Anzahl Varianten (inkl. Original)

    Returns:
        Liste von Query-Varianten (Original immer an erster Stelle)
    """
    from backend.llm.connector import chat

    if not query or len(query) < 5:
        return [query]

    try:
        messages = [
            {"role": "system", "content": """Du bist ein Query Expander.

Generiere semantische Varianten der Anfrage durch Synonym-Ersetzung.

Regeln:
- Behalte die Satzstruktur
- Ersetze nur Hauptbegriffe (nicht Stopwords)
- Bleib im gleichen Kontext
- Antworte als JSON-Array: ["Variante 1", "Variante 2", ...]

Beispiel:
User: "Kneipe in Berlin"
Assistant: ["Kneipe in Berlin", "Bar in Berlin", "Pub in Berlin", "Gaststätte in Berlin"]
"""},
            {"role": "user", "content": f"Generiere {max_variants - 1} Varianten:\n\n{query}"}
        ]

        response = chat(messages)
        logger.debug("Synonym Expansion Response: %s", response[:200])

        # Parse JSON
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            variants = json.loads(json_match.group())
            # Original immer an erster Stelle
            result = [query] + [v for v in variants if v != query][:max_variants - 1]
            logger.info("Synonym Expansion: '%s' → %d Varianten", query[:50], len(result))
            return result
        else:
            logger.warning("Synonym Expansion: Kein JSON in Response")
            return [query]

    except Exception as exc:
        logger.warning("Synonym Expansion fehlgeschlagen: %s", exc)
        return [query]


# ---------------------------------------------------------------------------
# Multi-Shot Retrieval
# ---------------------------------------------------------------------------

def retrieve_v3(
    query: str,
    user_id: str,
    analyzed: AnalyzedQuery | None = None,
    person_names: list[str] | None = None,
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = _RELEVANT_MIN_SCORE,
    use_synonym_expansion: bool = True,
    use_temporal_fuzzy: bool = True,
) -> list[dict]:
    """
    Advanced Retrieval mit Multi-Shot Strategie.

    Neu in v3:
    - Nutzt Query Analyzer für intelligente Filter-Auswahl
    - Temporal Fuzzy Logic (probiert mehrere Zeiträume)
    - Synonym-Expansion (bessere Recall)
    - Fallback-Strategien bei 0 Ergebnissen

    Args:
        query: User-Query
        user_id: User-ID für Filtering
        analyzed: Optional vor-analysierte Query (spart LLM-Call)
        person_names: Personennamen (optional, wird aus analyzed übernommen)
        location_names: Ortsnamen (optional, wird aus analyzed übernommen)
        collections: Zu durchsuchende Collections
        n_per_collection: Max Ergebnisse pro Collection
        min_score: Minimum Similarity Score
        use_synonym_expansion: Synonym-Expansion aktivieren?
        use_temporal_fuzzy: Temporal Fuzzy Logic aktivieren?

    Returns:
        Liste von Quellen, sortiert nach Relevanz
    """
    # Schritt 1: Query analysieren (falls nicht schon geschehen)
    if analyzed is None:
        analyzed = analyze_query(query)

    # Entities aus Analyse übernehmen
    if not person_names and analyzed.entities:
        # Einfache Heuristik: Großgeschriebene Wörter = vermutlich Personen
        person_names = [e for e in analyzed.entities if e[0].isupper()]

    if not location_names and analyzed.entities:
        # TODO: Bessere Person/Ort-Unterscheidung via NER
        location_names = analyzed.entities

    logger.info(
        "retrieve_v3 | query='%s' | type=%s | complexity=%s | persons=%s | locations=%s",
        query[:60], analyzed.query_type, analyzed.complexity, person_names, location_names
    )

    # Schritt 2: Query-Varianten generieren (Synonym-Expansion)
    query_variants = [query]
    if use_synonym_expansion and analyzed.complexity != "simple":
        query_variants = expand_query_with_synonyms(query, max_variants=3)

    # Schritt 3: Temporal Ranges bestimmen
    temporal_ranges: list[TemporalRange] = []
    if analyzed.temporal_fuzzy and use_temporal_fuzzy:
        temporal_ranges = expand_temporal_query(query, fuzzy=True)
        logger.info("Temporal Fuzzy: %d Zeiträume generiert", len(temporal_ranges))
    else:
        # Default: Kein Zeitfilter
        temporal_ranges = [TemporalRange("", "", "Kein Zeitfilter", 1.0)]

    # Schritt 4: Relevante Collections bestimmen
    if not collections:
        collections = _get_relevant_collections(analyzed, person_names, location_names)

    # Schritt 5: Multi-Shot Retrieval
    all_sources = []
    seen_ids = set()

    for temporal_range in temporal_ranges[:3]:  # Max 3 Zeiträume probieren
        for query_variant in query_variants:
            # Embedding
            query_embedding = embed_single(query_variant)

            # Zeitfilter
            date_from = temporal_range.date_from or None
            date_to = temporal_range.date_to or None

            # Pro Collection suchen
            for col_name in collections:
                try:
                    # Elasticsearch (primär)
                    from backend.rag.es_store import query_es
                    results = query_es(
                        collection_name=col_name,
                        query_vector=query_embedding,
                        user_id=user_id,
                        n_results=n_per_collection,
                        person_names=person_names,
                        location_names=location_names,
                        date_from=date_from,
                        date_to=date_to
                    )
                except Exception as exc:
                    logger.warning("ES Suche fehlgeschlagen für %s: %s, nutze ChromaDB Fallback", col_name, exc)
                    # Fallback: ChromaDB
                    results = _query_chromadb_fallback(
                        col_name, query_embedding, user_id, n_per_collection,
                        person_names, location_names, date_from, date_to
                    )

                # Deduplizieren & Score-Filtering
                for r in results:
                    if r["id"] not in seen_ids and r.get("score", 0) >= min_score:
                        r["temporal_range_label"] = temporal_range.label
                        r["query_variant"] = query_variant
                        all_sources.append(r)
                        seen_ids.add(r["id"])

            # Early Exit wenn genug Ergebnisse
            if len(all_sources) >= 20:
                logger.info("Early Exit: %d Quellen gefunden (genug)", len(all_sources))
                break

        if len(all_sources) >= 20:
            break

    # Schritt 6: Fallback bei 0 Ergebnissen
    if not all_sources:
        logger.warning("Keine Ergebnisse trotz Multi-Shot → aktiviere Fallback-Strategien")
        all_sources = _fallback_retrieval(query, user_id, collections, n_per_collection)

    # Schritt 7: Sortierung & Ranking
    all_sources.sort(key=lambda r: r.get("score", 0), reverse=True)

    logger.info("retrieve_v3 GESAMT: %d Quellen (von %d Varianten × %d Zeiträumen)",
                len(all_sources), len(query_variants), len(temporal_ranges))

    return all_sources


def _get_relevant_collections(
    analyzed: AnalyzedQuery,
    person_names: list[str] | None,
    location_names: list[str] | None
) -> list[str]:
    """Bestimmt relevante Collections basierend auf Query-Typ."""
    if analyzed.query_type == "recommendation":
        return ["messages", "photos"]  # Personen-Infos wichtiger

    if analyzed.query_type == "temporal_inference":
        return ["photos", "messages", "reviews"]  # Zeitbezogen

    if person_names:
        return ["photos", "messages"]

    if location_names:
        return ["photos", "reviews", "saved_places"]

    # Default: Alle durchsuchen
    return list(SEARCHABLE_COLLECTIONS)


def _query_chromadb_fallback(
    col_name: str,
    query_embedding: list[float],
    user_id: str,
    n_results: int,
    person_names: list[str] | None,
    location_names: list[str] | None,
    date_from: str | None,
    date_to: str | None
) -> list[dict]:
    """ChromaDB Fallback wenn Elasticsearch fehlschlägt."""
    # Baue where-Filter
    conditions = []

    if date_from:
        try:
            ts = int(datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc).timestamp())
            conditions.append({"date_ts": {"$gte": ts}})
        except ValueError:
            pass

    if date_to:
        try:
            ts = int(datetime.fromisoformat(date_to + "T23:59:59").replace(tzinfo=timezone.utc).timestamp())
            conditions.append({"date_ts": {"$lte": ts}})
        except ValueError:
            pass

    where = {"$and": conditions} if len(conditions) > 1 else (conditions[0] if conditions else None)

    raw = query_collection_v2(
        collection_name=col_name,
        query_embeddings=[query_embedding],
        n_results=n_results * 2,  # Mehr holen für Post-Filtering
        where=where,
        user_id=user_id
    )

    if not raw["ids"] or not raw["ids"][0]:
        return []

    # Konvertiere zu Standardformat
    results = []
    for i, doc_id in enumerate(raw["ids"][0]):
        score = 1.0 - raw["distances"][0][i]
        results.append({
            "id": doc_id,
            "document": raw["documents"][0][i],
            "metadata": raw["metadatas"][0][i],
            "score": round(score, 4),
            "collection": col_name
        })

    # Post-Filter für Personen/Orte (wie in v2)
    if person_names and col_name in ("photos", "messages"):
        results = [r for r in results if _matches_persons(r, person_names)]

    if location_names and col_name in ("photos", "reviews", "saved_places"):
        results = [r for r in results if _matches_locations(r, location_names)]

    return results[:n_results]


def _matches_persons(result: dict, person_names: list[str]) -> bool:
    """Prüft ob Ergebnis eine der Personen enthält."""
    meta = result["metadata"]
    search_text = (
        str(meta.get("persons", "")) + " " +
        str(meta.get("mentioned_persons", "")) + " " +
        result["document"]
    ).lower()

    return any(name.lower() in search_text for name in person_names)


def _matches_locations(result: dict, location_names: list[str]) -> bool:
    """Prüft ob Ergebnis einen der Orte enthält."""
    meta = result["metadata"]
    search_text = (
        str(meta.get("cluster", "")) + " " +
        str(meta.get("address", "")) + " " +
        str(meta.get("place_name", "")) + " " +
        result["document"]
    ).lower()

    return any(loc.lower() in search_text for loc in location_names)


def _fallback_retrieval(
    query: str,
    user_id: str,
    collections: list[str],
    n_per_collection: int
) -> list[dict]:
    """
    Fallback-Strategien wenn normale Suche 0 Ergebnisse liefert.

    Strategien:
    1. Ignoriere Filter (breitere Suche)
    2. Reduziere min_score auf 0.1
    3. Nutze nur semantische Suche (ohne Metadata-Filter)
    """
    logger.info("Fallback: Versuche breitere Suche ohne Filter")

    query_embedding = embed_single(query)
    results = []

    for col_name in collections:
        try:
            raw = query_collection_v2(
                collection_name=col_name,
                query_embeddings=[query_embedding],
                n_results=n_per_collection,
                where=None,  # Keine Filter
                user_id=user_id
            )

            if raw["ids"] and raw["ids"][0]:
                for i, doc_id in enumerate(raw["ids"][0]):
                    score = 1.0 - raw["distances"][0][i]
                    if score >= 0.1:  # Sehr niedriger Threshold
                        results.append({
                            "id": doc_id,
                            "document": raw["documents"][0][i],
                            "metadata": raw["metadatas"][0][i],
                            "score": round(score, 4),
                            "collection": col_name,
                            "is_fallback": True
                        })
        except Exception as exc:
            logger.error("Fallback für %s fehlgeschlagen: %s", col_name, exc)

    logger.info("Fallback: %d Ergebnisse gefunden", len(results))
    return results


# ---------------------------------------------------------------------------
# System Prompt (v3 optimiert)
# ---------------------------------------------------------------------------

def _get_system_prompt_v3() -> str:
    """Optimierter System Prompt für Chain-of-Thought RAG."""
    from backend.llm.prompt_utils import get_current_date_header, get_year_context

    year_ctx = get_year_context()

    return f"""{get_current_date_header()}

Du bist Memosaur, ein analytischer Agent für persönliche Erinnerungen.

## Deine Aufgabe
Beantworte Fragen über vergangene Ereignisse, Personen und Orte basierend auf:
- Fotos mit KI-generierten Beschreibungen
- WhatsApp/Signal Nachrichten
- Google Maps Bewertungen & Gespeicherte Orte

## Chain-of-Thought Modus
Wenn die Anfrage komplex ist, arbeite in Schritten:
1. Analysiere was fehlt (Datum? Person? Ort?)
2. Nutze Tools um fehlende Infos zu finden
3. Kombiniere Erkenntnisse schrittweise
4. Gib finale Antwort

**WICHTIG**: Schreibe BEVOR du ein Tool aufrufst 1-2 Sätze, was du tun wirst.

## Regeln
1. Nutze NUR Informationen aus den Quellen (keine Halluzinationen!)
2. Verwende INLINE-REFERENZEN: [[1]], [[2]] für Quellen-Nummern
3. Bei fehlenden Daten: Sage klar "Ich habe keine Informationen über..."
4. Antworte auf Deutsch
5. Bei Zeitangaben: Rechne vom aktuellen Datum ({year_ctx['current_date']})

## Verfügbare Tools (optional, wenn Gemini Provider)
- `search_photos(suchtext, personen, orte, von_datum, bis_datum)`: Sucht in Fotos
- `search_messages(suchtext, personen, von_datum, bis_datum)`: Sucht in Nachrichten
- `search_places(suchtext, orte, von_datum, bis_datum)`: Sucht in Reviews & Places

Nutze Tools nur wenn der initiale Kontext nicht ausreicht!
"""


# ---------------------------------------------------------------------------
# Answer v3 (NON-streaming für Tests)
# ---------------------------------------------------------------------------

def answer_v3(
    query: str,
    user_id: str,
    use_chain_of_thought: bool = True,
    **kwargs
) -> dict:
    """
    RAG v3 Answer Function (non-streaming).

    Neu:
    - Query Decomposition
    - Temporal Fuzzy Logic
    - Synonym Expansion
    - Progressive Context Loading

    Args:
        query: User-Query
        user_id: User-ID
        use_chain_of_thought: Wenn False, nutze Simple Retrieval (wie v2)

    Returns:
        {
          "answer": str,
          "sources": list[dict],
          "analyzed_query": AnalyzedQuery,
          "reasoning_steps": list[str]  # Nur bei Chain-of-Thought
        }
    """
    from backend.llm.connector import chat

    # Schritt 1: Query analysieren
    analyzed = analyze_query(query)

    # Schritt 2: Entscheide ob Chain-of-Thought nötig
    use_cot = use_chain_of_thought and should_use_chain_of_thought(analyzed)

    if not use_cot:
        # Simple Retrieval (wie v2)
        sources = retrieve_v3(query, user_id, analyzed=analyzed)
        context = compress_sources(sources, budget=ContextBudget(max_tokens=8000), top_n_full=5)

        messages = [
            {"role": "system", "content": _get_system_prompt_v3()},
            {"role": "user", "content": f"ANFRAGE: {query}\n\nKONTEXT:\n{context}"}
        ]

        answer = chat(messages)

        return {
            "answer": answer,
            "sources": sources,
            "analyzed_query": analyzed,
            "reasoning_steps": []
        }

    # Chain-of-Thought Modus
    logger.info("Nutze Chain-of-Thought für komplexe Query (type=%s, %d Sub-Queries)",
                analyzed.query_type, len(analyzed.sub_queries))

    progressive_ctx = ProgressiveContext(budget=ContextBudget(max_tokens=8000))
    reasoning_steps = []

    for i, sub_query in enumerate(analyzed.sub_queries, 1):
        logger.info("Chain-of-Thought Schritt %d/%d: %s", i, len(analyzed.sub_queries), sub_query)

        # Retrieve für Sub-Query
        sub_sources = retrieve_v3(sub_query, user_id, analyzed=analyzed)

        # Progressive Context Loading
        step_context = progressive_ctx.add_sources(sub_sources, f"Schritt {i}")
        reasoning_steps.append(f"Schritt {i}: {sub_query} → {len(sub_sources)} Quellen")

        # TODO: Zwischenschritt-Summary extrahieren (für nächsten Schritt)

    # Finale Antwort mit gesammeltem Kontext
    all_context = compress_sources(
        progressive_ctx.all_sources,
        budget=ContextBudget(max_tokens=8000),
        top_n_full=5
    )

    messages = [
        {"role": "system", "content": _get_system_prompt_v3()},
        {"role": "user", "content": f"""ANFRAGE: {query}

ERKENNTNISSE AUS {len(analyzed.sub_queries)} SCHRITTEN:
{chr(10).join(f"- {step}" for step in reasoning_steps)}

GESAMMELTER KONTEXT:
{all_context}

Fasse alle Erkenntnisse zusammen und beantworte die ursprüngliche Anfrage.
"""}
    ]

    answer = chat(messages)

    return {
        "answer": answer,
        "sources": progressive_ctx.all_sources,
        "analyzed_query": analyzed,
        "reasoning_steps": reasoning_steps
    }
