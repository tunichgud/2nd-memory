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
from datetime import datetime, timezone, timedelta

from backend.rag.embedder import embed_single
from backend.rag.store_v2 import query_collection_v2
from backend.rag.store import COLLECTIONS, SEARCHABLE_COLLECTIONS

logger = logging.getLogger(__name__)

_RELEVANT_MIN_SCORE  = 0.20
_FALLBACK_MIN_SCORE  = 0.42

def _get_system_prompt() -> str:
    now = datetime.now()
    current_date = now.strftime('%d.%m.%Y')
    current_weekday = now.strftime('%A')  # Monday, Tuesday, etc.
    weekday_map = {
        'Monday': 'Montag', 'Tuesday': 'Dienstag', 'Wednesday': 'Mittwoch',
        'Thursday': 'Donnerstag', 'Friday': 'Freitag', 'Saturday': 'Samstag', 'Sunday': 'Sonntag'
    }
    weekday_de = weekday_map.get(current_weekday, current_weekday)

    return f"""⚠️ WICHTIG - AKTUELLES DATUM: {current_date} ({weekday_de})

Zeitliche Berechnungen IMMER von diesem Datum aus:
- "letztes Wochenende" = Samstag {(now - timedelta(days=now.weekday()+2)).strftime('%d.%m.%Y')} + Sonntag {(now - timedelta(days=now.weekday()+1)).strftime('%d.%m.%Y')}
- "diese Woche" = {(now - timedelta(days=now.weekday())).strftime('%d.%m.%Y')} bis {(now + timedelta(days=6-now.weekday())).strftime('%d.%m.%Y')}
- "gestern" = {(now - timedelta(days=1)).strftime('%d.%m.%Y')}
- "vorgestern" = {(now - timedelta(days=2)).strftime('%d.%m.%Y')}

Du bist ein analytischer Agent (Memosaur) für ein persönliches Gedächtnis-System.
Du hilfst dem Benutzer, sich an Ereignisse, Orte, Personen und Erlebnisse zu erinnern.

WICHTIG: Nutze für Personen und Orte immer die echten Namen aus der Anfrage oder den Quellen. 

ReAct (Reasoning and Acting) Ansatz:
- Plane in Schritten! Wenn der Nutzer eine komplexe Frage stellt, überlege erst:
  * Welche Informationen fehlen mir noch (Datum, Ort, Personen)?
  * Beispiel: "Wie ging es Sarah, als ich mit Nora in München war?"
    -> Schritt 1: Finde das Datum des München-Aufenthalts mit Nora via search_photos(personen=["Nora"], orte=["München"]).
    -> Schritt 2: Suche gezielt nach Nachrichten von Sarah in diesem Zeitraum.

- WICHTIG FÜR TRANSPARENZ: Bevor du ein Tool aufrufst, schreibe IMMER 1-2 Sätze auf, was du als Nächstes tun wirst und warum. Sende diese Gedanken ALS TEXT, BEVOR du den Tool-Aufruf auslöst.

Weitere Regeln:
1. Nutze ausschließlich die bereitgestellten Quellen und Tools. Halluziniere keine Fakten.
2. Nenne die exakte Quellenart und das Datum bei jeder Information (Foto, Bewertung, Nachricht).
3. Nutze INLINE-REFERENZEN: Wenn du dich auf eine Information aus dem Kontext (INITIALER KONTEXT oder Tool-Ergebnisse) beziehst, setze die Nummer der Quelle in doppelte eckige Klammern, z.B. [[1]], [[2]]. Das Frontend macht daraus interaktive Buttons.
4. Antworte auf Deutsch. Falls nach "Gefühlen" oder "Stimmung" gefragt wird, nutze `search_messages`.
5. Bei Ortsfragen: nutze das Cluster/Ort-Feld ("München-Ost") und GPS-Koordinaten zur Verortung.
6. Falls keine passenden Daten gefunden wurden, erkläre logisch, was du versucht hast zu suchen und warum es keine Treffer gab."""


def _build_token_filter(
    date_from: str | None,
    date_to: str | None,
) -> dict | None:
    """
    Baut ChromaDB where-Filter nur für Datumsangaben.
    Personen und Orte werden nun via Python Post-Filtering iteriert.
    """
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

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def retrieve_v2(
    query: str,
    user_id: str,
    person_names: list[str] | None = None,
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = _RELEVANT_MIN_SCORE,
    date_from: str | None = None,
    date_to: str | None = None,
    **kwargs # Catch-all für veraltete Parameter wie masked_query/person_tokens
) -> list[dict]:
    """User-scoped semantisches Retrieval mit Python Post-Filtern für Personen und Orte."""
    # Support für veraltete Parameter-Namen (Bugfix)
    effective_query = kwargs.get("masked_query", query)
    effective_persons = person_names or kwargs.get("person_tokens") or []
    effective_locations = location_names or kwargs.get("location_tokens") or []

    query_embedding = embed_single(effective_query)
    effective_persons = [n.strip() for n in effective_persons if n.strip()]
    effective_locations = [n.strip() for n in effective_locations if n.strip()]

    # Personen-Namen auflösen (z.B. "Ringo" -> ["Ringo", "cluster_5", "0123..."])
    resolved_person_identifiers = _resolve_person_names(effective_persons)
    logger.info("v2 resolved identifiers: %s -> %s", effective_persons, resolved_person_identifiers)

    # Relevante Collections bestimmen
    has_person = bool(person_names)
    has_location = bool(location_names)
    if collections:
        relevant = set(collections)
    elif has_person and not has_location:
        relevant = {"photos", "messages"}
    elif has_location and not has_person:
        relevant = {"photos", "reviews", "saved_places"}
    else:
        relevant = set(SEARCHABLE_COLLECTIONS)

    logger.info(
        "v2 retrieve | query='%s' | persons=%s | locations=%s | relevant=%s",
        effective_query[:60], effective_persons, effective_locations, sorted(relevant),
    )

    # --- NEU: Elasticsearch Integration ---
    from backend.rag.es_store import query_es as _query_es
    try:
        es_results = []
        for col_name in collections:
            is_relevant = col_name in (relevant or [])
            es_hits = _query_es(
                collection_name=col_name,
                query_vector=query_embedding,
                user_id=user_id,
                n_results=n_per_collection,
                person_names=resolved_person_identifiers, # Nutze aufgelöste IDs
                location_names=effective_locations,
                date_from=date_from,
                date_to=date_to
            )
            if es_hits:
                logger.debug("  [%s] Elasticsearch Treffer: %d", col_name, len(es_hits))
                for h in es_hits:
                    h["is_relevant"] = is_relevant
                es_results.extend(es_hits)
        
        if es_results:
            es_results.sort(key=lambda r: (r.get("is_relevant", False), r.get("score", 0)), reverse=True)
            logger.info("v2 ES retrieve GESAMT: %d Ergebnisse", len(es_results))
            return es_results
            
    except Exception as exc:
        logger.warning("Elasticsearch Suche fehlgeschlagen, Fallback auf ChromaDB: %s", exc)

    # --- ALT: ChromaDB + Python Post-Filtering (Fallback) ---
    all_results: list[dict] = []

    for col_name in SEARCHABLE_COLLECTIONS:
        is_relevant = col_name in relevant
        threshold = min_score if is_relevant else _FALLBACK_MIN_SCORE

        where = _build_token_filter(date_from, date_to)

        logger.info("  [%s] relevant=%s | where=%s", col_name, is_relevant, where)

        fetch_n = n_per_collection
        if (effective_locations or effective_persons):
            # Da ChromaDB substring checks ($contains) nicht unterstützt,
            # holen wir einen vergrößerten semantischen Pool und filtern via Python
            fetch_n = 50

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

        # --- Post-Filter für Personen ---
        if effective_persons and col_name in ("photos", "messages"):
            pers_lower = [n.lower() for n in resolved_person_identifiers] # Nutze aufgelöste IDs
            filtered_by_person = []
            for h in col_hits:
                meta = h["metadata"]
                search_text = (
                    str(meta.get("persons", "")) + " " + 
                    str(meta.get("mentioned_persons", "")) + " " + 
                    str(meta.get("people", "")) + " " +
                    str(meta.get("cluster_id", "")) + " " + # WICHTIG: cluster_id aus vision
                    h["document"]
                ).lower()
                
                if any(p in search_text for p in pers_lower):
                    filtered_by_person.append(h)
                    
            if filtered_by_person:
                logger.info("  [%s] person-Post-Filter: %d → %d Treffer (Identifier=%s)",
                            col_name, len(col_hits), len(filtered_by_person), resolved_person_identifiers)
                col_hits = filtered_by_person
            else:
                logger.info("  [%s] person-Post-Filter ohne Treffer (Identifier=%s) – verwerfe alle!",
                            col_name, resolved_person_identifiers)
                col_hits = []

        # --- Post-Filter für Orte ---
        if effective_locations and col_name in ("photos", "reviews", "saved_places"):
            loc_lower = [n.lower() for n in effective_locations]
            filtered_by_loc = []
            for h in col_hits:
                meta = h["metadata"]
                search_text = (
                    str(meta.get("cluster", "")) + " " + 
                    str(meta.get("address", "")) + " " + 
                    str(meta.get("name", "")) + " " +
                    str(meta.get("place_name", "")) + " " +
                    h["document"]
                ).lower()
                
                if any(loc in search_text for loc in loc_lower):
                    filtered_by_loc.append(h)
                    
            if filtered_by_loc:
                logger.info("  [%s] loc-Post-Filter: %d → %d Treffer (Namen=%s)",
                            col_name, len(col_hits), len(filtered_by_loc), location_names)
                col_hits = filtered_by_loc
            else:
                logger.info("  [%s] loc-Post-Filter ohne Treffer (Namen=%s) – verwerfe alle!",
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
    logger.info("v2 retrieve GESAMT: %d Ergebnisse für '%s'", len(all_results), effective_query[:40])
    return all_results


def _resolve_person_names(names: list[str]) -> list[str]:
    """Löst Klarnamen via ES Entity-Index in alle bekannten Identifier auf."""
    if not names: return []
    try:
        from backend.rag.es_store import get_es_client, get_index_name
        es = get_es_client()
        idx = get_index_name("entities")
        
        resolved = set()
        for name in names:
            resolved.add(name) # Den Namen selbst immer behalten
            # Suche in ES
            try:
                res = es.get(index=idx, id=name)
                entity = res["_source"]
                # Aliase hinzufügen
                for a in entity.get("chat_aliases", []): resolved.add(a)
                # Cluster-IDs hinzufügen
                for c in entity.get("vision_clusters", []): resolved.add(c)
            except Exception:
                # Falls exakter Name nicht gefunden, versuche Match
                try:
                    search = es.search(index=idx, query={"match": {"entity_id": name}})
                    for hit in search["hits"]["hits"]:
                        ent = hit["_source"]
                        resolved.add(ent["entity_id"])
                        for a in ent.get("chat_aliases", []): resolved.add(a)
                        for c in ent.get("vision_clusters", []): resolved.add(c)
                except Exception:
                    pass
        return list(resolved)
    except Exception as exc:
        logger.warning("Personen-Auflösung via ES fehlgeschlagen: %s", exc)
        return names



import json

def _format_sources_for_llm(sources: list[dict], use_compression: bool = False) -> str:
    """Bereitet die Retrieval-Ergebnisse als str auf.

    Args:
        sources: Liste von Source-Dicts
        use_compression: Wenn True, nutze intelligente Context-Kompression (empfohlen für >15 Quellen)
    """
    if use_compression:
        # Nutze intelligente Context-Kompression (seit v2.1)
        from backend.rag.context_manager import compress_sources, ContextBudget
        budget = ContextBudget(max_tokens=8000)  # Sicheres Limit für Chain-of-Thought
        return compress_sources(sources, budget=budget, top_n_full=5)

    # Legacy-Formatierung (für Kompatibilität)
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
        # HINWEIS: 'persons'-Feld absichtlich weggelassen – unterschiedliche Token-Namespaces
        # zwischen Foto-Import und Anfrage würden den Agenten verwirren (z.B. [PER_1] bedeutet
        # im Foto-Import eine andere Person als [PER_1] in der Nutzeranfrage).
        # Der Agent soll Personen aus dem Dokumenttext (Fotobeschreibung) ableiten.
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
        query=masked_query,
        user_id=user_id,
        person_names=person_tokens,
        location_names=location_names,
        collections=collections,
        n_per_collection=n_per_collection,
        min_score=min_score,
        date_from=date_from,
        date_to=date_to,
    )

    # Nutze Kompression wenn viele Quellen
    use_compression = len(sources) > 15
    context = _format_sources_for_llm(sources, use_compression=use_compression)

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
            query=suchtext,
            user_id=user_id,
            person_names=pers_toks,
            location_names=loc_names, # Merged loc_toks into names if needed?
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
        # Nutze Kompression wenn viele Quellen
        use_compression = len(res) > 15
        return _format_sources_for_llm(res, use_compression=use_compression)

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
            query=suchtext,
            user_id=user_id,
            person_names=pers_toks,
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
        # Nutze Kompression wenn viele Quellen
        use_compression = len(res) > 15
        return _format_sources_for_llm(res, use_compression=use_compression)

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
    query: str,
    user_id: str,
    chat_history: list[dict] | None = None,
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
        parsed = parse_query(query)
        if parsed.locations:
            plain_locs = [l for l in parsed.locations if not l.startswith("[LOC_")]
            if plain_locs:
                logger.info("Stream-Fallback: LLM-Parser fand Klarnamen-Orte: %s", plain_locs)
                location_names = list(location_names or []) + plain_locs
        if parsed.persons:
            plain_pers = [p for p in parsed.persons if not p.startswith("[PER_")]
            if plain_pers:
                logger.info("Stream-Fallback: LLM-Parser fand Klarnamen-Personen: %s", plain_pers)
                person_names = list(person_names or []) + plain_pers
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
            query=query,
            user_id=user_id,
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
        loc_names = [l.strip() for l in (orte or []) if l.strip()]
        pers_names = [p.strip() for p in (personen or []) if p.strip()]

        # ReAct Disambiguierung
        from backend.ingestion.persons import get_known_persons
        known = get_known_persons()
        for p_name in pers_names:
            matches = list(set([k for k in known if p_name.lower() in k.lower() and " " in k]))
            if len(matches) > 1:
                return (f"Observation: Fehler. Der Name '{p_name}' ist mehrdeutig. "
                        f"Bekannte Personen in der Datenbank sind: {', '.join(matches)}. "
                        f"Bitte stoppe deine Suche und frage den User im Chat direkt, welche Person genau gemeint ist.")

        # Suchtext anreichern mit aufgelösten Ortsnamen wenn vorhanden
        effective_query = suchtext or ""
        if loc_names and not effective_query:
            effective_query = " ".join(loc_names)

        res = retrieve_v2(
            query=effective_query,
            user_id=user_id,
            person_names=pers_names,
            location_names=loc_names,
            collections=["photos"],
            n_per_collection=n_per_collection,
            min_score=min_score,
            date_from=von_datum,
            date_to=bis_datum,
        )
        logger.info(f"===> search_photos GOT {len(res)} results.")
        for r in res[:3]:
            logger.info(f"     -> {r['id']}: cluster={r['metadata'].get('cluster')}, score={r['score']}")
        existing_ids = {s["id"] for s in sources}
        new_sources = []
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                new_sources.append(s)
                existing_ids.add(s["id"])
        
        # Nutze Kompression für Tool-Results
        use_compression = len(res) > 15
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res, use_compression=use_compression)})

    def search_messages(
        suchtext: str = "",
        personen: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
    ) -> str:
        logger.info(f"==> Stream Tool Call: search_messages({suchtext}, {personen}, {von_datum}, {bis_datum})")
        pers_names = [p.strip() for p in (personen or []) if p.strip()]

        # ReAct Disambiguierung
        from backend.ingestion.persons import get_known_persons
        known = get_known_persons()
        for p_name in pers_names:
            matches = list(set([k for k in known if p_name.lower() in k.lower() and " " in k]))
            if len(matches) > 1:
                return (f"Observation: Fehler. Der Name '{p_name}' ist mehrdeutig. "
                        f"Bekannte Personen in der Datenbank sind: {', '.join(matches)}. "
                        f"Bitte stoppe deine Suche und frage den User im Chat direkt, welche Person genau gemeint ist.")

        res = retrieve_v2(
            query=suchtext,
            user_id=user_id,
            person_names=pers_names,
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
                
        # Nutze Kompression für Tool-Results
        use_compression = len(res) > 15
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res, use_compression=use_compression)})

    def search_places(
        suchtext: str = "",
        orte: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
    ) -> str:
        logger.info(f"==> Stream Tool Call: search_places({suchtext}, {orte}, {von_datum}, {bis_datum})")
        loc_names = [l.strip() for l in (orte or []) if l.strip()]

        res = retrieve_v2(
            query=suchtext,
            user_id=user_id,
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
                
        # Nutze Kompression für Tool-Results
        use_compression = len(res) > 15
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res, use_compression=use_compression)})

    # Nutze Kompression wenn viele Quellen
    use_compression = len(sources) > 15
    context = _format_sources_for_llm(sources, use_compression=use_compression)

    filter_parts = []
    if date_from or date_to:
        filter_parts.append(f"Datum: {date_from or '?'} bis {date_to or '?'}")

    filter_note = f"\nErkannte Zeitfilter: {'; '.join(filter_parts)}" if filter_parts else ""

    user_prompt = (
        f"NUTZERANFRAGE:\n{query}\n"
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

    messages = [{"role": "system", "content": sys_prompt}]
    
    if chat_history:
        # Beschränke auf die letzten 10 Nachrichten, um Context Window zu schonen
        for msg in chat_history[-10:]:
            # connector.py erwartet 'assistant' statt 'model'
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": msg["content"]})

    messages.append({"role": "user", "content": user_prompt})

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
