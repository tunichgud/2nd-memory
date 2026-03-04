"""
retriever.py – RAG-Retrieval und LLM-Antwort-Generierung für memosaur.

Ablauf einer Abfrage:
  1. Query parsen (LLM-basiert) → Personen, Datum, Collections, Metadaten-Filter
  2. Gefiltertes Retrieval pro Collection (semantisch + Metadaten-Filter)
  3. Adaptive Slot-Vergabe: nur relevante Collections bekommen Pflicht-Slots
  4. Kontext für LLM aufbauen (mit Quellentyp-Labels)
  5. LLM-Antwort generieren
"""

from __future__ import annotations

import logging
from datetime import datetime

from backend.rag.embedder import embed_single
from backend.rag.store import query_collection, COLLECTIONS
from backend.rag.query_parser import ParsedQuery, parse_query, summarize

logger = logging.getLogger(__name__)

# Mindest-Score für Collections die NICHT als relevant erkannt wurden
_FALLBACK_MIN_SCORE = 0.42

# Mindest-Score für relevante Collections
_RELEVANT_MIN_SCORE = 0.20

SYSTEM_PROMPT = """Du bist ein persönliches Gedächtnis-System namens Memosaur.
Du hilfst dem Benutzer, sich an Ereignisse, Orte, Personen und Erlebnisse aus seinem Leben zu erinnern.

Dir stehen folgende Informationsquellen zur Verfügung:
- 📷 Fotos mit GPS-Koordinaten, Datum, Personen und KI-Beschreibungen
- ⭐ Google Maps Bewertungen von besuchten Restaurants und Orten
- 📍 Gespeicherte Orte aus Google Maps
- 💬 WhatsApp/Signal Nachrichten

Wichtige Regeln:
1. Beziehe ALLE bereitgestellten Quellen in deine Antwort ein.
2. Nenne bei jeder Information explizit die Quellenart: "Laut einem Foto vom...", "Laut deiner Bewertung...", "In einer Nachricht vom..."
3. Wenn eine Person in einer Nachricht erwähnt wird (nicht nur als Absender), ist das ebenfalls eine valide Quelle.
4. Antworte präzise, persönlich und immer auf Deutsch.
5. Falls keine passenden Daten vorhanden sind, sage das klar."""


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    parsed: ParsedQuery | None = None,
    n_per_collection: int = 6,
) -> list[dict]:
    """Sucht relevante Dokumente mit geparsten Filtern.

    Args:
        query: Originale Suchanfrage
        parsed: Bereits geparste Query (wird neu geparst wenn None)
        n_per_collection: Max. Ergebnisse pro Collection

    Returns:
        Sortierte Liste von Ergebnis-Dicts
    """
    if parsed is None:
        parsed = parse_query(query)

    query_embedding = embed_single(query)
    relevant_cols = set(parsed.relevant_collections) if parsed.relevant_collections else set(COLLECTIONS)

    all_results: list[dict] = []

    for col_name in COLLECTIONS:
        is_relevant = col_name in relevant_cols
        where_filter = parsed.metadata_filters.get(col_name) if parsed.metadata_filters else None
        min_score = _RELEVANT_MIN_SCORE if is_relevant else _FALLBACK_MIN_SCORE

        try:
            raw = query_collection(
                collection_name=col_name,
                query_embeddings=[query_embedding],
                n_results=n_per_collection,
                where=where_filter,
            )
        except Exception as exc:
            logger.warning("Retrieval-Fehler in '%s': %s", col_name, exc)
            # Bei Filter-Fehler (z.B. leere Collection oder ungültiger Filter) ohne Filter wiederholen
            try:
                raw = query_collection(
                    collection_name=col_name,
                    query_embeddings=[query_embedding],
                    n_results=n_per_collection,
                    where=None,
                )
            except Exception:
                continue

        if not raw["ids"] or not raw["ids"][0]:
            continue

        col_hits: list[dict] = []
        for i, doc_id in enumerate(raw["ids"][0]):
            distance = raw["distances"][0][i]
            score = 1.0 - distance

            col_hits.append({
                "id": doc_id,
                "document": raw["documents"][0][i],
                "metadata": raw["metadatas"][0][i],
                "score": round(score, 4),
                "collection": col_name,
                "is_relevant_collection": is_relevant,
                "filter_applied": where_filter is not None,
            })

        if not col_hits:
            continue

        # Für relevante Collections: Top-2 immer nehmen + weitere über Schwellwert
        # Für irrelevante Collections: nur über hohem Schwellwert
        if is_relevant:
            guaranteed = col_hits[:2]
            extras = [h for h in col_hits[2:] if h["score"] >= min_score]
            all_results.extend(guaranteed + extras)
        else:
            all_results.extend([h for h in col_hits if h["score"] >= min_score])

    # Nach Score sortieren, aber relevante Collections bevorzugen
    all_results.sort(
        key=lambda r: (r["is_relevant_collection"], r["score"]),
        reverse=True,
    )

    logger.info(
        "Retrieve '%s': %d Ergebnisse aus %d Collections (relevant: %s)",
        query[:50], len(all_results),
        len({r["collection"] for r in all_results}),
        sorted(relevant_cols),
    )
    return all_results


# ---------------------------------------------------------------------------
# Kontext aufbauen
# ---------------------------------------------------------------------------

SOURCE_LABELS = {
    "photos":       ("📷", "FOTO"),
    "reviews":      ("⭐", "GOOGLE MAPS BEWERTUNG"),
    "saved_places": ("📍", "GESPEICHERTER ORT"),
    "messages":     ("💬", "NACHRICHT"),
}


def _build_context(sources: list[dict]) -> str:
    """Baut den Kontext-String für den LLM-Prompt auf."""
    if not sources:
        return "Keine passenden Einträge in der Datenbank gefunden."

    parts = []
    for i, src in enumerate(sources[:12], start=1):
        meta = src["metadata"]
        icon, label = SOURCE_LABELS.get(src["collection"], ("📄", src["collection"].upper()))
        score_pct = int(src["score"] * 100)

        # Metadaten-Zusammenfassung je nach Quellentyp
        meta_parts = []
        if src["collection"] == "photos":
            if meta.get("date_iso"):
                try:
                    dt = datetime.fromisoformat(meta["date_iso"])
                    meta_parts.append(dt.strftime("%d.%m.%Y %H:%M"))
                except ValueError:
                    meta_parts.append(meta["date_iso"])
            if meta.get("place_name"):
                meta_parts.append(meta["place_name"])
            elif meta.get("lat") and meta.get("lat") != 0:
                meta_parts.append(f"{meta['lat']:.4f}°N {meta['lon']:.4f}°E")
            if meta.get("persons"):
                meta_parts.append(f"Personen: {meta['persons']}")
        elif src["collection"] in ("reviews", "saved_places"):
            if meta.get("name"):
                meta_parts.append(meta["name"])
            if meta.get("address"):
                meta_parts.append(meta["address"])
            if meta.get("date_iso"):
                meta_parts.append(meta["date_iso"][:10])
        elif src["collection"] == "messages":
            if meta.get("chat_name"):
                meta_parts.append(f"Chat: {meta['chat_name']}")
            if meta.get("date_iso"):
                meta_parts.append(meta["date_iso"][:10])
            if meta.get("mentioned_persons"):
                meta_parts.append(f"Erwähnte Personen: {meta['mentioned_persons']}")
            elif meta.get("persons"):
                meta_parts.append(f"Teilnehmer: {meta['persons']}")

        header = f"[Quelle {i} – {icon} {label} | Relevanz: {score_pct}%]"
        if meta_parts:
            header += f"\n{' | '.join(meta_parts)}"

        parts.append(f"{header}\n{src['document']}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Vollständige RAG-Pipeline
# ---------------------------------------------------------------------------

def answer(
    query: str,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = 0.20,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Vollständige RAG-Pipeline: Parse → Retrieve → Generate.

    Returns:
        Dict mit keys: answer, sources, query, parsed_query
    """
    from backend.llm.connector import chat

    # 1. Query parsen
    parsed = parse_query(query)

    # Manuelle Overrides (aus API-Parametern)
    if collections:
        parsed.relevant_collections = collections
    if date_from:
        parsed.date_from = date_from
    if date_to:
        parsed.date_to = date_to
    # Filter neu berechnen wenn Overrides gesetzt
    if date_from or date_to or collections:
        from backend.rag.query_parser import _build_metadata_filters
        _build_metadata_filters(parsed)

    # 2. Retrieval
    sources = retrieve(query, parsed=parsed, n_per_collection=n_per_collection)

    # 3. Kontext aufbauen
    context = _build_context(sources)

    # 4. Filter-Zusammenfassung für den Prompt
    filter_summary = summarize(parsed)
    filter_note = f"\nErkannte Suchfilter: {filter_summary}" if filter_summary else ""

    # 5. LLM-Anfrage
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Kontext aus meinen persönlichen Daten:{filter_note}\n\n"
                f"{context}\n\n"
                f"Meine Frage: {query}"
            ),
        },
    ]

    llm_answer = chat(messages)

    return {
        "query": query,
        "answer": llm_answer,
        "sources": sources,
        "parsed_query": {
            "persons": parsed.persons,
            "locations": parsed.locations,
            "date_from": parsed.date_from,
            "date_to": parsed.date_to,
            "relevant_collections": parsed.relevant_collections,
            "filter_summary": filter_summary,
        },
    }
