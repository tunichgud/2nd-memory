"""
retriever_v2.py – Token-aware RAG-Retrieval für memosaur v2.

Unterschiede zu retriever.py (v1):
  - Kein LLM-basierter Query-Parser (NER findet im Browser statt)
  - Strukturierte Filter kommen als Token-IDs vom Frontend
  - Alle ChromaDB-Queries sind user_id-gefiltert
  - Ein- und Ausgabe enthalten nur Tokens, keine Klarnamen
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from backend.rag.embedder import embed_single
from backend.rag.store_v2 import query_collection_v2, COLLECTIONS
from backend.rag.store import COLLECTIONS

logger = logging.getLogger(__name__)

_RELEVANT_MIN_SCORE  = 0.20
_FALLBACK_MIN_SCORE  = 0.42

SYSTEM_PROMPT_V2 = """Du bist ein persönliches Gedächtnis-System namens Memosaur.
Du hilfst dem Benutzer, sich an Ereignisse, Orte, Personen und Erlebnisse zu erinnern.

WICHTIG: Alle Personen- und Ortsnamen in deinen Quellen sind durch Tokens ersetzt
(z.B. [PER_1] für eine Person, [LOC_2] für einen Ort). Verwende diese Tokens
EXAKT so in deiner Antwort – ersetze sie NICHT durch echte Namen.
Das System wird die Tokens später automatisch in echte Namen umwandeln.

Regeln:
1. Nutze ausschließlich die bereitgestellten Quellen.
2. Behalte alle Tokens ([PER_n], [LOC_n], [ORG_n]) unverändert in deiner Antwort.
3. Nenne die Quellenart bei jeder Information (Foto, Bewertung, Nachricht).
4. Antworte auf Deutsch.
5. Falls keine passenden Daten vorhanden sind, sage das klar."""


def _build_token_filter(
    person_tokens: list[str],
    location_tokens: list[str],
    date_from: str | None,
    date_to: str | None,
    user_id: str,
    collection: str,
) -> dict | None:
    """
    Baut ChromaDB where-Filter aus Token-IDs und Datumsangaben.
    Token-Flags sind im Format: has_per_1, has_loc_2 etc.
    """
    conditions = []

    # Datumsfilter
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

    # Personen-Filter via Boolean-Felder (has_per_1, has_per_2 ...)
    if collection in ("photos", "messages") and person_tokens:
        for tok in person_tokens:
            # "[PER_1]" → "has_per_1"
            clean = tok.strip("[]").lower()
            field = f"has_{clean}"
            conditions.append({field: {"$eq": True}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def retrieve_v2(
    masked_query: str,
    user_id: str,
    person_tokens: list[str] | None = None,
    location_tokens: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = _RELEVANT_MIN_SCORE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """User-scoped semantisches Retrieval mit Token-Filtern."""
    query_embedding = embed_single(masked_query)
    person_tokens = person_tokens or []
    location_tokens = location_tokens or []

    # Relevante Collections bestimmen
    has_person = bool(person_tokens)
    has_location = bool(location_tokens)
    if collections:
        relevant = set(collections)
    elif has_person and not has_location:
        relevant = {"photos", "messages"}
    elif has_location and not has_person:
        relevant = {"photos", "reviews", "saved_places"}
    else:
        relevant = set(COLLECTIONS)

    all_results: list[dict] = []

    for col_name in COLLECTIONS:
        is_relevant = col_name in relevant
        threshold = min_score if is_relevant else _FALLBACK_MIN_SCORE

        where = _build_token_filter(
            person_tokens, location_tokens, date_from, date_to, user_id, col_name
        )

        raw = query_collection_v2(
            collection_name=col_name,
            query_embeddings=[query_embedding],
            n_results=n_per_collection,
            where=where,
            user_id=user_id,
        )

        if not raw["ids"] or not raw["ids"][0]:
            continue

        col_hits = []
        for i, doc_id in enumerate(raw["ids"][0]):
            score = 1.0 - raw["distances"][0][i]
            col_hits.append({
                "id": doc_id,
                "document": raw["documents"][0][i],
                "metadata": raw["metadatas"][0][i],
                "score": round(score, 4),
                "collection": col_name,
                "is_relevant": is_relevant,
            })

        if is_relevant:
            all_results.extend(col_hits[:2])
            all_results.extend([h for h in col_hits[2:] if h["score"] >= threshold])
        else:
            all_results.extend([h for h in col_hits if h["score"] >= threshold])

    all_results.sort(key=lambda r: (r["is_relevant"], r["score"]), reverse=True)
    logger.info("v2 retrieve '%s': %d Ergebnisse", masked_query[:40], len(all_results))
    return all_results


def answer_v2(
    masked_query: str,
    user_id: str,
    person_tokens: list[str] | None = None,
    location_tokens: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = _RELEVANT_MIN_SCORE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Vollständige v2 RAG-Pipeline. Antwortet mit Tokens."""
    from backend.llm.connector import chat

    sources = retrieve_v2(
        masked_query=masked_query,
        user_id=user_id,
        person_tokens=person_tokens,
        location_tokens=location_tokens,
        collections=collections,
        n_per_collection=n_per_collection,
        min_score=min_score,
        date_from=date_from,
        date_to=date_to,
    )

    SOURCE_LABELS = {
        "photos":       ("📷", "FOTO"),
        "reviews":      ("⭐", "BEWERTUNG"),
        "saved_places": ("📍", "GESPEICHERTER ORT"),
        "messages":     ("💬", "NACHRICHT"),
    }

    if sources:
        parts = []
        for i, src in enumerate(sources[:12], start=1):
            meta = src["metadata"]
            icon, label = SOURCE_LABELS.get(src["collection"], ("📄", src["collection"].upper()))
            pct = int(src["score"] * 100)

            meta_parts = []
            if meta.get("date_iso"):
                meta_parts.append(meta["date_iso"][:10])
            if meta.get("place_name"):
                meta_parts.append(meta["place_name"])   # Bereits ein Token z.B. [LOC_2]
            if meta.get("persons"):
                meta_parts.append(f"Personen: {meta['persons']}")
            if meta.get("name"):
                meta_parts.append(meta["name"])

            header = f"[Quelle {i} – {icon} {label} | {pct}%]"
            if meta_parts:
                header += f"\n{' | '.join(meta_parts)}"
            parts.append(f"{header}\n{src['document']}")
        context = "\n\n---\n\n".join(parts)
    else:
        context = "Keine passenden Einträge gefunden."

    # Token-Zusammenfassung für Prompt
    filter_parts = []
    if person_tokens:
        filter_parts.append(f"Personen: {', '.join(person_tokens)}")
    if location_tokens:
        filter_parts.append(f"Orte: {', '.join(location_tokens)}")
    if date_from:
        filter_parts.append(f"Ab: {date_from}")
    if date_to:
        filter_parts.append(f"Bis: {date_to}")
    filter_summary = " · ".join(filter_parts)

    filter_note = f"\nErkannte Filter: {filter_summary}" if filter_summary else ""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_V2},
        {
            "role": "user",
            "content": (
                f"Kontext aus persönlichen Daten:{filter_note}\n\n"
                f"{context}\n\n"
                f"Frage: {masked_query}"
            ),
        },
    ]

    llm_answer = chat(messages)

    return {
        "masked_query": masked_query,
        "answer": llm_answer,
        "sources": sources,
        "filter_summary": filter_summary,
    }
