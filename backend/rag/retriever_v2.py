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

def _get_system_prompt() -> str:
    from datetime import datetime
    current_date = datetime.now().strftime('%d.%m.%Y')
    return f"""Du bist ein analytischer Agent (Memosaur) für ein persönliches Gedächtnis-System.
Du hilfst dem Benutzer, sich an Ereignisse, Orte, Personen und Erlebnisse zu erinnern.

HEUTIGES DATUM: {current_date} (Nutze dies als Referenz für Begriffe wie "letztes Jahr", "letzten Monat" etc.)

WICHTIG: Alle Personen- und Ortsnamen in deinen Quellen sind durch Tokens ersetzt
(z.B. [PER_1] für eine Person, [LOC_2] für einen Ort). Verwende diese Tokens
EXAKT so in deiner Antwort – ersetze sie NICHT durch echte Namen.
Das System wird die Tokens später automatisch in echte Namen umwandeln.

ReAct (Reasoning and Acting) Ansatz:
- Plane in Schritten! Wenn der Nutzer eine komplexe Frage stellt, überlege erst:
  * Gibt es mehrere Entitäten (Personen/Orte), die NICHT im selben Kontext auftauchen?
  * Beispiel: "Wie ging es [PER_1], als ich mit [PER_2] in [LOC_1] war?"
    -> FALSCH: search_photos(personen=["[PER_1]", "[PER_2]"]). Das findet Bilder, auf denen BEIDE sind (die es nicht gibt).
    -> RICHTIG Schritt 1: Finde das Datum des Ausflugs via search_photos(personen=["[PER_2]"], orte=["[LOC_1]"]).
    -> RICHTIG Schritt 2: Suche Nachrichten von [PER_1] in dem gefundenen Datums-Zeitraum via search_messages(personen=["[PER_1]"], von_datum="...", bis_datum="...").

Weitere Regeln:
1. Nutze ausschließlich die bereitgestellten Quellen und Tools. Halluziniere keine Orte oder Personen.
2. Behalte alle Tokens ([PER_n], [LOC_n], [ORG_n]) unverändert in deiner Antwort.
3. Nenne die exakte Quellenart und das Datum bei jeder Information (Foto, Bewertung, Nachricht).
4. Antworte auf Deutsch. Falls Sentiment oder Emotionen gefragt sind, werte alle relevanten Texte tiefgreifend aus.
5. Bei Ortsfragen: nutze das Cluster/Ort-Feld ("München-Ost") und GPS-Koordinaten zur Verortung.
6. Falls keine passenden Daten gefunden wurden, erkläre logisch, was du versucht hast zu suchen und warum es keine Treffer gab."""


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

    # HINWEIS: has_loc_x-Filter wird NICHT angewendet, da Token-IDs
    # zwischen Browser-Sessions inkonsistent sein können (Token-Inkonsistenz-Bug).
    # Location-Filtering erfolgt semantisch + via cluster-Klartext im LLM-Kontext.

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
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = _RELEVANT_MIN_SCORE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """User-scoped semantisches Retrieval mit Token-Filtern."""
    query_embedding = embed_single(masked_query)
    person_tokens   = person_tokens or []
    location_tokens = location_tokens or []
    location_names  = [n.strip() for n in (location_names or []) if n.strip()]

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

    logger.info(
        "v2 retrieve | query='%s' | persons=%s | locations=%s | relevant=%s",
        masked_query[:60], person_tokens, location_tokens, sorted(relevant),
    )

    all_results: list[dict] = []

    for col_name in COLLECTIONS:
        is_relevant = col_name in relevant
        threshold = min_score if is_relevant else _FALLBACK_MIN_SCORE

        where = _build_token_filter(
            person_tokens, location_tokens, date_from, date_to, user_id, col_name
        )

        logger.info("  [%s] relevant=%s | where=%s", col_name, is_relevant, where)

        fetch_n = n_per_collection
        if location_names and col_name in ("photos", "reviews", "saved_places"):
            # Semantische Suche ist dumm für konkrete Orte. Hole großen Pool für Post-Filter.
            fetch_n = 60

        raw = query_collection_v2(
            collection_name=col_name,
            query_embeddings=[query_embedding],
            n_results=fetch_n,
            where=where,
            user_id=user_id,
        )

        if not raw["ids"] or not raw["ids"][0]:
            logger.info("  [%s] → 0 Treffer (Collection leer oder Filter schlägt zu restriktiv an)", col_name)
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

        # --- Location-Post-Filter via cluster-Klartext ---
        # Wenn Ortsnamen bekannt sind (vom Browser aus IndexedDB), filtern wir
        # photos/reviews/saved_places auf cluster-Feld (Substring, case-insensitive).
        # Dieser Filter ist robuster als has_loc_x da er auf Klarnamen arbeitet.
        if location_names and col_name in ("photos", "reviews", "saved_places"):
            loc_lower = [n.lower() for n in location_names]
            filtered = [
                h for h in col_hits
                if any(
                    loc in h["metadata"].get("cluster", "").lower() or
                    loc in h["metadata"].get("address",  "").lower() or
                    loc in h["metadata"].get("name",     "").lower()
                    for loc in loc_lower
                )
            ]
            if filtered:
                logger.info("  [%s] cluster-Post-Filter: %d → %d Treffer (Namen=%s)",
                            col_name, len(col_hits), len(filtered), location_names)
                col_hits = filtered
            else:
                logger.info("  [%s] cluster-Post-Filter ohne Treffer (Namen=%s) – verwerfe alle!",
                            col_name, location_names)
                col_hits = []

        # Kürzen auf n_per_collection, falls wir vorher fetch_n hochgesetzt haben
        if len(col_hits) > n_per_collection:
            col_hits = col_hits[:n_per_collection]

        # Scores loggen
        score_summary = [(h["id"][:30], h["score"]) for h in col_hits[:5]]
        logger.info("  [%s] → %d Treffer, Top-Scores: %s (threshold=%.2f)",
                    col_name, len(col_hits), score_summary, threshold)

        if is_relevant:
            all_results.extend(col_hits[:2])
            all_results.extend([h for h in col_hits[2:] if h["score"] >= threshold])
        else:
            all_results.extend([h for h in col_hits if h["score"] >= threshold])

    all_results.sort(key=lambda r: (r["is_relevant"], r["score"]), reverse=True)
    logger.info("v2 retrieve GESAMT: %d Ergebnisse für '%s'", len(all_results), masked_query[:40])
    return all_results



import json

def _format_sources_for_llm(sources: list[dict]) -> str:
    """Bereitet die Retrieval-Ergebnisse als str auf."""
    SOURCE_LABELS = {
        "photos":       ("📷", "FOTO"),
        "reviews":      ("⭐", "BEWERTUNG"),
        "saved_places": ("📍", "GESPEICHERTER ORT"),
        "messages":     ("💬", "NACHRICHT"),
    }
    if not sources:
        return "Keine passenden Einträge gefunden."

    parts = []
    for i, src in enumerate(sources[:12], start=1):
        meta = src["metadata"]
        icon, label = SOURCE_LABELS.get(src["collection"], ("📄", src["collection"].upper()))
        pct = int(src["score"] * 100)

        meta_parts = []
        if meta.get("date_iso"):
            meta_parts.append(meta["date_iso"][:10])
        if meta.get("cluster"):
            meta_parts.append(f"Cluster/Ort: {meta['cluster']}")
        elif meta.get("place_name"):
            meta_parts.append(meta["place_name"])
        if meta.get("lat") and meta.get("lat") != 0.0:
            meta_parts.append(f"GPS: {meta['lat']:.3f}°N {meta['lon']:.3f}°E")
        if meta.get("persons"):
            meta_parts.append(f"Personen: {meta['persons']}")
        if meta.get("name"):
            meta_parts.append(meta["name"])
        if meta.get("address"):
            meta_parts.append(f"Adresse: {meta['address']}")

        header = f"[Quelle {i} – {icon} {label} | {pct}%]"
        if meta_parts:
            header += f"\n{' | '.join(meta_parts)}"
        parts.append(f"{header}\n{src['document']}")
    return "\n\n---\n\n".join(parts)


def answer_v2(
    masked_query: str,
    user_id: str,
    person_tokens: list[str] | None = None,
    location_tokens: list[str] | None = None,
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = _RELEVANT_MIN_SCORE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Vollständige v2 RAG-Pipeline. Antwortet mit Tokens."""
    from backend.llm.connector import chat, get_cfg
    from backend.rag.query_parser import parse_query

    # 1. Fallback: Parse query via LLM if frontend NER missed anything (e.g., short queries like "in München")
    # This acts as a safety net. Anything already masked (like [LOC_1]) will be ignored or safely skipped.
    parsed = parse_query(masked_query)
    
    if parsed.locations:
        locs = [l for l in parsed.locations if not l.startswith("[LOC_")]
        if locs:
            logger.info("Fallback-Parser fand Klartext-Orte: %s", locs)
            location_names = (location_names or []) + locs
            
    if parsed.persons:
        pers = [p for p in parsed.persons if not p.startswith("[PER_")]
        if pers:
            logger.info("Fallback-Parser fand Klartext-Personen: %s", pers)
            person_tokens = (person_tokens or []) + pers
            
    if parsed.date_from and not date_from:
        date_from = parsed.date_from
    if parsed.date_to and not date_to:
        date_to = parsed.date_to

    sources = retrieve_v2(
        masked_query=masked_query,
        user_id=user_id,
        person_tokens=person_tokens,
        location_tokens=location_tokens,
        location_names=location_names,
        collections=collections,
        n_per_collection=n_per_collection,
        min_score=min_score,
        date_from=date_from,
        date_to=date_to,
    )

    context = _format_sources_for_llm(sources)

    # Definition der spezialisierten Agenten-Tools
    def search_photos(
        suchtext: str = "",
        personen: list[str] | None = None,
        orte: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
    ) -> str:
        """Sucht gezielt in der Foto-Datenbank des Nutzers nach Aufnahmen, Orten und visuellen Momenten.
        
        Args:
            suchtext: Wonach auf den Bildern gesucht werden soll (z.B. "Am Strand", "Urlaub").
            personen: Liste von Personen-Tokens (z.B. ["[PER_1]"]).
            orte: Liste von Orts-Tokens oder Klarnamen (z.B. ["[LOC_1]", "München"]).
            von_datum: Startdatum im Format YYYY-MM-DD (optional).
            bis_datum: Enddatum im Format YYYY-MM-DD (optional).
        """
        logger.info(f"==> Tool Call: search_photos(suchtext='{suchtext[:30]}...', personen={personen}, orte={orte}, von={von_datum}, bis={bis_datum})")
        loc_toks = [l for l in (orte or []) if l.startswith("[LOC_")]
        loc_names = [l for l in (orte or []) if not l.startswith("[LOC_")]
        pers_toks = [p for p in (personen or []) if p.startswith("[PER_")]

        res = retrieve_v2(
            masked_query=suchtext,
            user_id=user_id,
            person_tokens=pers_toks,
            location_tokens=loc_toks,
            location_names=loc_names,
            collections=["photos"],
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=von_datum,
            date_to=bis_datum,
        )
        existing_ids = {s["id"] for s in sources}
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                existing_ids.add(s["id"])
        return _format_sources_for_llm(res)

    def search_messages(
        suchtext: str = "",
        personen: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
    ) -> str:
        """Sucht gezielt in den Textnachrichten und Chatverläufen des Nutzers (WhatsApp/Signal).
        Ideal um Emotionen, Unterhaltungen und Stimmungen herauszufinden.

        Args:
            suchtext: Inhalt der gesuchten Nachrichten (z.B. "Wie geht es dir?", "Treffen").
            personen: Liste von Personen-Tokens mit denen geschrieben wurde (z.B. ["[PER_1]"]).
            von_datum: Startdatum im Format YYYY-MM-DD (optional).
            bis_datum: Enddatum im Format YYYY-MM-DD (optional).
        """
        logger.info(f"==> Tool Call: search_messages(suchtext='{suchtext[:30]}...', personen={personen}, von={von_datum}, bis={bis_datum})")
        pers_toks = [p for p in (personen or []) if p.startswith("[PER_")]
        res = retrieve_v2(
            masked_query=suchtext,
            user_id=user_id,
            person_tokens=pers_toks,
            location_tokens=None,
            location_names=None,
            collections=["messages"],
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=von_datum,
            date_to=bis_datum,
        )
        existing_ids = {s["id"] for s in sources}
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                existing_ids.add(s["id"])
        return _format_sources_for_llm(res)

    # Zusammenfassung für User/Prompt
    filter_parts = []
    if person_tokens:
        filter_parts.append(f"Personen: {', '.join(person_tokens)}")
    if location_names:
        filter_parts.append(f"Orte (Klartext): {', '.join(location_names)}")
    elif location_tokens:
        filter_parts.append(f"Orte: {', '.join(location_tokens)}")
    if date_from:
        filter_parts.append(f"Ab: {date_from}")
    if date_to:
        filter_parts.append(f"Bis: {date_to}")
    filter_summary = " · ".join(filter_parts)

    filter_note = f"\nErkannte Suchfilter: {filter_summary}" if filter_summary else ""

    user_prompt = (
        f"NUTZERANFRAGE:\n{masked_query}\n\n"
        f"FILTER-INFORMATIONEN (aus Frontend):{filter_note}\n\n"
        f"INITIALER KONTEXT AUS DER DATENBANK:\n{context}\n\n"
        f"ANWEISUNG:\n"
        f"1. Analysiere die NUTZERANFRAGE und den INITIALEN KONTEXT.\n"
        f"2. Wenn die Informationen nicht für eine vollständige Antwort reichen, nutze deine Tools "
        f"(`search_photos`, `search_messages`), um weitere Fakten zu sammeln. Bspw. kannst du erst Fotos suchen, "
        f"um ein genaues Datum herauszufinden, und dann Chatnachrichten für diesen spezifischen Zeitraum mit dem anderen Tool laden.\n"
        f"3. Falls Sentiment oder Emotionen gefragt sind, werte alle relevanten Texte und Fotobeschreibungen aktiv aus.\n"
        f"4. Kombiniere schlussendlich alle gesammelten Fakten zu einer hilfreichen Antwort."
    )
    sys_prompt = _get_system_prompt()
    logger.info("=== DEBUG LLM PROMPT (AGENTIC RAG) ===")
    logger.info("SYSTEM:\n%s", sys_prompt)
    logger.info("USER:\n%s", user_prompt[:800] + "\n...[truncated_for_log]")
    logger.info("======================================")

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Nur Gemini unterstützt aktuell Tool-Calling über unser Wrapper-Framework
    cfg = get_cfg()
    use_tools = [search_photos, search_messages] if cfg.get("llm", {}).get("provider") == "gemini" else None

    llm_answer = chat(messages, tools=use_tools)

    return {
        "masked_query": masked_query,
        "answer": llm_answer,
        "sources": sources, # Frontend bekommt jetzt auch Tools-Sources!
        "filter_summary": filter_summary,
    }

async def answer_v2_stream(
    masked_query: str,
    user_id: str,
    person_tokens: list[str] | None = None,
    location_tokens: list[str] | None = None,
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = 0.2,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Asynchroner Generator für Agentic RAG.
    Yields JSON-Strings für Server-Sent Events (SSE).
    """
    from backend.llm.connector import chat_stream, get_cfg
    import json

    # Fallback: Parse die Anfrage via LLM, um Klarnamen-Orte zu extrahieren,
    # die das Frontend-NER möglicherweise nicht erkannt hat (z.B. "München" statt "[LOC_1]").
    try:
        from backend.rag.query_parser import parse_query
        parsed = parse_query(masked_query)
        if parsed.locations:
            plain_locs = [l for l in parsed.locations if not l.startswith("[LOC_")]
            if plain_locs:
                logger.info("Stream-Fallback: LLM-Parser fand Klarnamen-Orte: %s", plain_locs)
                location_names = list(location_names or []) + plain_locs
        if parsed.persons:
            plain_pers = [p for p in parsed.persons if not p.startswith("[PER_")]
            if plain_pers:
                logger.info("Stream-Fallback: LLM-Parser fand Klarnamen-Personen: %s", plain_pers)
                person_tokens = list(person_tokens or []) + plain_pers
        if parsed.date_from and not date_from:
            date_from = parsed.date_from
        if parsed.date_to and not date_to:
            date_to = parsed.date_to
    except Exception as exc:
        logger.warning("Query-Parser Fallback fehlgeschlagen: %s", exc)

    # 1. Start-Kontext: Für echte ReAct-Agenten starten wir leer, 
    # damit die Tools explizit und präzise aufgerufen werden.
    cfg = get_cfg()
    provider = cfg.get("llm", {}).get("provider")
    is_gemini = provider == "gemini"

    if is_gemini:
        sources = []
        # Initiale Quellen (leer) sofort ans Frontend schicken
        yield json.dumps({
            "type": "sources",
            "content": sources
        }) + "\n\n"
    else:
        # Fallback für dumme Modelle
        sources = retrieve_v2(
            masked_query=masked_query,
            user_id=user_id,
            person_tokens=person_tokens,
            location_tokens=location_tokens,
            location_names=location_names,
            collections=collections,
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=date_from,
            date_to=date_to,
        )
        yield json.dumps({
            "type": "sources",
            "content": sources
        }) + "\n\n"

    def search_photos(
        suchtext: str = "",
        personen: list[str] | None = None,
        orte: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
    ) -> str:
        logger.info(f"==> Stream Tool Call: search_photos({suchtext}, {personen}, {orte}, {von_datum}, {bis_datum})")
        loc_toks = [l for l in (orte or []) if l.startswith("[LOC_")]
        loc_names = [l for l in (orte or []) if not l.startswith("[LOC_")]
        pers_toks = [p for p in (personen or []) if p.startswith("[PER_")]

        # Token-to-Name Mapping aus Frontend-Kontext
        if location_tokens and location_names:
            for tok in loc_toks:
                try:
                    idx = location_tokens.index(tok)
                    resolved = location_names[idx]
                    if resolved not in loc_names:
                        loc_names.append(resolved)
                except ValueError:
                    pass

        # WICHTIG: Wenn ein Ort gefiltert wird, darf der Personen-Filter NICHT
        # als harter ChromaDB-Filter laufen – Fotos in München haben oft nur
        # `has_per_1=True` (den User selbst), aber der Agent sucht nach `[PER_2]` (z.B. Nora).
        # Der Orts-Cluster-Post-Filter ist robuster. Personen-Prüfung passiert durch den LLM.
        effective_pers_toks = [] if loc_names else pers_toks

        # Suchtext anreichern mit aufgelösten Ortsnamen wenn vorhanden
        effective_query = suchtext or ""
        if loc_names and not effective_query:
            effective_query = " ".join(loc_names)

        res = retrieve_v2(
            masked_query=effective_query,
            user_id=user_id,
            person_tokens=effective_pers_toks,
            location_tokens=loc_toks,
            location_names=loc_names,
            collections=["photos"],
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=von_datum,
            date_to=bis_datum,
        )
        logger.info(f"===> search_photos GOT {len(res)} results. effective_pers_toks={effective_pers_toks}, loc_names={loc_names}")
        for r in res[:3]:
            logger.info(f"     -> {r['id']}: cluster={r['metadata'].get('cluster')}, score={r['score']}")
        existing_ids = {s["id"] for s in sources}
        new_sources = []
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                new_sources.append(s)
                existing_ids.add(s["id"])
        
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res)})

    def search_messages(
        suchtext: str = "",
        personen: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
    ) -> str:
        logger.info(f"==> Stream Tool Call: search_messages({suchtext}, {personen}, {von_datum}, {bis_datum})")
        pers_toks = [p for p in (personen or []) if p.startswith("[PER_")]
        res = retrieve_v2(
            masked_query=suchtext,
            user_id=user_id,
            person_tokens=pers_toks,
            location_tokens=None,
            location_names=None,
            collections=["messages"],
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=von_datum,
            date_to=bis_datum,
        )
        existing_ids = {s["id"] for s in sources}
        new_sources = []
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                new_sources.append(s)
                existing_ids.add(s["id"])
                
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res)})

    def search_places(
        suchtext: str = "",
        orte: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
    ) -> str:
        logger.info(f"==> Stream Tool Call: search_places({suchtext}, {orte}, {von_datum}, {bis_datum})")
        loc_toks = [l for l in (orte or []) if l.startswith("[LOC_")]
        loc_names = [l for l in (orte or []) if not l.startswith("[LOC_")]

        # Token-to-Name Mapping aus Frontend-Kontext
        if location_tokens and location_names:
            for tok in loc_toks:
                try:
                    idx = location_tokens.index(tok)
                    resolved = location_names[idx]
                    if resolved not in loc_names:
                        loc_names.append(resolved)
                except ValueError:
                    pass

        res = retrieve_v2(
            masked_query=suchtext,
            user_id=user_id,
            person_tokens=None,
            location_tokens=loc_toks,
            location_names=loc_names,
            collections=["reviews", "saved_places"],
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=von_datum,
            date_to=bis_datum,
        )
        existing_ids = {s["id"] for s in sources}
        new_sources = []
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                new_sources.append(s)
                existing_ids.add(s["id"])
                
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res)})

    context = _format_sources_for_llm(sources)

    # Baue eine Token→Klarname-Tabelle für den Agenten
    token_map_parts = []
    if location_tokens and location_names:
        for tok, name in zip(location_tokens, location_names):
            token_map_parts.append(f"  {tok} = '{name}'")
    
    token_map_note = ""
    if token_map_parts:
        token_map_note = "\n\nTOKEN-MAPPING (nutze diese echten Namen in Tool-Aufrufen!):\n" + "\n".join(token_map_parts)
    elif location_names:
        # Nur Klarnamen vorhanden (aus Fallback-Parser), kein Mapping
        token_map_note = f"\n\nRELEVANTE ORTE (aus Anfrage erkannt): {', '.join(location_names)}"

    filter_parts = []
    if date_from or date_to:
        filter_parts.append(f"Datum: {date_from or '?'} bis {date_to or '?'}")

    filter_note = f"\nErkannte Zeitfilter: {'; '.join(filter_parts)}" if filter_parts else ""

    user_prompt = (
        f"NUTZERANFRAGE:\n{masked_query}\n"
        f"{token_map_note}"
        f"{filter_note}\n\n"
        f"INITIALER KONTEXT AUS DER DATENBANK:\n{context}\n\n"
        f"ANWEISUNG:\n"
        f"1. Analysiere die NUTZERANFRAGE.\n"
        f"2. Da der INITIALE KONTEXT leer ist, MUSST du aktiv Tools "
        f"(`search_photos`, `search_messages`, `search_places`) nutzen, um Fakten zu sammeln. "
        f"(`search_places` sucht in Restaurantbewertungen und gespeicherten Orten).\n"
        f"3. Falls Sentiment oder Emotionen gefragt sind, werte alle relevanten Texte und Fotobeschreibungen aktiv aus.\n"
        f"4. Kombiniere schlussendlich alle gesammelten Fakten zu einer hilfreichen Antwort."
    )
    sys_prompt = _get_system_prompt()

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]

    use_tools = [search_photos, search_messages, search_places] if is_gemini else None

    # LLM Stream asynchron konsumieren
    async for chunk in chat_stream(messages, tools=use_tools):
        # chunk ist dict: {"type": "plan" | "text", "content": "..."}
        if chunk["type"] == "plan":
            yield json.dumps({"type": "plan", "content": chunk["content"]}) + "\n\n"
        elif chunk["type"] == "text":
            # Bei Tool-Calls haben die Tools evtl. neue Sources an das globale sources array gehangen
            # Wir feuern nochmal ein Source-Update mit dem kompletten Set (oder Frontend merged)
            yield json.dumps({"type": "sources", "content": sources}) + "\n\n"
            yield json.dumps({"type": "text", "content": chunk["content"]}) + "\n\n"
