"""
retriever_v2.py – RAG-Retrieval für memosaur v2.

Unterschiede zu retriever.py (v1):
  - Kein LLM-basierter Query-Parser
  - Strukturierte Filter (Personen, Orte, Datum) kommen als Klarnamen vom Frontend
  - Alle ChromaDB-Queries sind user_id-gefiltert
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta

from backend.rag.embedder import embed_single
from backend.rag.store import SEARCHABLE_COLLECTIONS

logger = logging.getLogger(__name__)

_RELEVANT_MIN_SCORE  = 0.20
_FALLBACK_MIN_SCORE  = 0.42

def _get_system_prompt() -> str:
    from backend.llm.prompt_utils import get_current_date_header

    return f"""{get_current_date_header()}

Du bist ein analytischer Agent (Memosaur) für ein persönliches Gedächtnis-System.
Du hilfst dem Benutzer, sich an Ereignisse, Orte, Personen und Erlebnisse zu erinnern.

🎯 WICHTIGSTE REGEL für "Wo war ich?"-Fragen:
1. Suche IMMER zuerst gezielt nach Fotos mit den genannten Filtern (Personen, Datum)
2. Extrahiere aus den Foto-Metadaten das "Stadtname:"-Feld oder "Ort:"-Feld. Das "Stadtname:"-Feld ist der EXAKTE STADTNAME — nutze immer diesen (z.B. "Ahrensburg", nicht "Hamburg-Ost")
3. Liste ALLE unterschiedlichen Städte/Orte auf, die in den Quellen auftauchen — auch wenn nur ein Foto aus diesem Ort stammt
4. Nenne die Orte als erste Information in deiner Antwort
5. Halte die Antwort KURZ (maximal 3-4 Sätze für einfache Ortsfragen)

BEISPIEL:
User: "Wo war ich im August 2022 mit Nora?"
→ Thought: Ich suche nach Fotos mit Nora im August 2022, um den Ort zu finden.
→ Tool: search_photos(personen=["Nora"], von_datum="2022-08-01", bis_datum="2022-08-31")
→ Observation: [Foto vom 15.08.2022, cluster="München-Schwabing", GPS: 48.16°N 11.58°E]
→ Antwort: "Du warst im August 2022 mit Nora in **München (Schwabing)** [[1]]. Auf dem Foto vom 15. August sieht man euch am Englischen Garten [[1]]."

ReAct (Reasoning and Acting) Ansatz:
- Plane in Schritten! Wenn der Nutzer eine komplexe Frage stellt, überlege erst:
  * Welche Informationen fehlen mir noch (Datum, Ort, Personen)?
  * Beispiel: "Wie ging es Sarah, als ich mit Nora in München war?"
    -> Schritt 1: Finde das Datum des München-Aufenthalts mit Nora via search_photos(personen=["Nora"], orte=["München"]).
    -> Schritt 2: Suche gezielt nach Nachrichten von Sarah in diesem Zeitraum.

- WICHTIG FÜR TRANSPARENZ: Bevor du ein Tool aufrufst, schreibe IMMER 1-2 Sätze auf, was du als Nächstes tun wirst und warum.

Weitere Regeln:
1. Nutze ausschließlich die bereitgestellten Quellen und Tools. Halluziniere NIEMALS Fakten.
2. Nenne die exakte Quellenart und das Datum bei jeder Information (Foto, Bewertung, Nachricht).
3. Nutze INLINE-REFERENZEN: Wenn du dich auf eine Information aus dem Kontext (INITIALER KONTEXT oder Tool-Ergebnisse) beziehst, setze die Nummer der Quelle in doppelte eckige Klammern, z.B. [[1]], [[2]]. Das Frontend macht daraus interaktive Buttons.
4. Antworte auf Deutsch. Falls nach "Gefühlen" oder "Stimmung" gefragt wird, nutze `search_messages`.
   Falls nach spezifischen Eigennamen (Haustiere, seltene Namen) gefragt wird, nutze `search_messages` mit `schluesselwoerter=["Name"]`.
5. Bei Ortsfragen: nutze das "Ort:"-Feld oder "Cluster/Ort:"-Feld aus den Quellen. Das "Ort:"-Feld ist immer der tatsächliche Ortsname (z.B. "Ahrensburg"), nutze es bevorzugt.
6. Falls keine passenden Daten für den gefragten Zeitraum gefunden wurden: Sage klar "Ich habe dazu keine Einträge in deinen Daten." NIEMALS Orte, Zeiten oder Namen erfinden die nicht in den Quellen stehen.
7. Falls nach einem heutigen Termin gefragt wird und keine aktuellen Quellen vorhanden sind: Gib an was die zuletzt gefundenen relevanten Daten zeigen und erkläre, dass für heute keine Einträge vorliegen.

ANTWORTSTIL:
- Präzise und kurz (3-4 Sätze für einfache Fragen)
- Exakte Ortsangaben ZUERST (z.B. "Du warst in München", nicht "Es gibt Fotos aus einer Stadt")
- Nutze Fettdruck für wichtige Informationen (Orte, Daten, Personen)"""


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
) -> list[dict]:
    """User-scoped semantisches Retrieval mit Python Post-Filtern für Personen und Orte."""
    effective_persons = [n.strip() for n in (person_names or []) if n.strip()]
    effective_locations = [n.strip() for n in (location_names or []) if n.strip()]

    query_embedding = embed_single(query)

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
        query[:60], effective_persons, effective_locations, sorted(relevant),
    )

    # --- Elasticsearch Retrieval ---
    from backend.rag.es_store import query_es as _query_es
    all_results: list[dict] = []
    for col_name in relevant:
        is_relevant = True
        try:
            es_hits = _query_es(
                collection_name=col_name,
                query_vector=query_embedding,
                user_id=user_id,
                n_results=n_per_collection,
                person_names=resolved_person_identifiers,
                location_names=effective_locations,
                date_from=date_from,
                date_to=date_to,
            )
            if es_hits:
                logger.debug("  [%s] Elasticsearch Treffer: %d", col_name, len(es_hits))
                for h in es_hits:
                    h["is_relevant"] = is_relevant
                all_results.extend(es_hits)
        except Exception as exc:
            logger.warning("  [%s] Elasticsearch Suche fehlgeschlagen: %s", col_name, exc)

    all_results.sort(key=lambda r: (r.get("is_relevant", False), r.get("score", 0)), reverse=True)
    logger.info("v2 ES retrieve GESAMT: %d Ergebnisse für '%s'", len(all_results), query[:40])

    # Neighbor-Expansion fuer messages: laedt je 1 Chunk vor/nach jedem Treffer
    from backend.rag.es_store import fetch_neighbors_es
    existing_ids: set[str] = {r["id"] for r in all_results}
    neighbors: list[dict] = []
    for hit in all_results:
        if hit.get("collection") != "messages":
            continue
        ts_sec = hit.get("metadata", {}).get("date_ts")
        if not ts_sec:
            continue
        chat_name = hit.get("metadata", {}).get("chat_name")
        if not chat_name:
            continue
        new_neighbors = fetch_neighbors_es(
            collection_name="messages",
            chat_name=chat_name,
            timestamp_ms=int(ts_sec) * 1000,
            user_id=user_id,
            n_before=1,
            n_after=1,
            exclude_ids=existing_ids,
        )
        for nb in new_neighbors:
            if nb["id"] not in existing_ids:
                existing_ids.add(nb["id"])
                neighbors.append(nb)

    if neighbors:
        logger.info(
            "v2 Neighbor-Expansion: %d zusaetzliche Chunks fuer '%s'",
            len(neighbors), query[:40],
        )
        all_results.extend(neighbors)

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
        budget = ContextBudget()
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
            # Wenn place_name eine andere Stadt nennt als der Cluster (z.B. cluster=Hamburg-Ost,
            # place_name=Ahrensburg), beide anzeigen – verhindert, dass LLM falschen Ort nennt
            place = meta.get("place_name", "")
            if place:
                city = place.split(",")[0].strip()
                if city.lower() not in meta["cluster"].lower():
                    meta_parts.append(f"Ort: {city}")
        elif meta.get("place_name"):
            meta_parts.append(meta["place_name"])
        if meta.get("lat") and meta.get("lat") != 0.0:
            meta_parts.append(f"GPS: {meta['lat']:.3f}°N {meta['lon']:.3f}°E")
        # HINWEIS: 'persons'-Feld absichtlich weggelassen – der Agent soll Personen
        # aus dem Dokumenttext (Fotobeschreibung) ableiten.
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
    query: str,
    user_id: str,
    person_names: list[str] | None = None,
    location_names: list[str] | None = None,
    collections: list[str] | None = None,
    n_per_collection: int = 6,
    min_score: float = _RELEVANT_MIN_SCORE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Vollständige v2 RAG-Pipeline."""
    from backend.llm.connector import chat, get_cfg
    from backend.rag.query_parser import parse_query
    from backend.rag.query_logger import start_trace

    trace = start_trace(query)

    # Fallback: Parse query via LLM to extract locations/persons the frontend may have missed
    parsed = parse_query(query)

    if parsed.locations:
        logger.info("Fallback-Parser fand Klartext-Orte: %s", parsed.locations)
        location_names = (location_names or []) + parsed.locations

    if parsed.persons:
        logger.info("Fallback-Parser fand Klartext-Personen: %s", parsed.persons)
        person_names = (person_names or []) + parsed.persons

    if parsed.date_from and not date_from:
        date_from = parsed.date_from
    if parsed.date_to and not date_to:
        date_to = parsed.date_to

    trace.log_parsed({
        "persons": person_names or [],
        "locations": location_names or [],
        "date_from": date_from,
        "date_to": date_to,
    })

    sources = retrieve_v2(
        query=query,
        user_id=user_id,
        person_names=person_names,
        location_names=location_names,
        collections=collections,
        n_per_collection=n_per_collection,
        min_score=min_score,
        date_from=date_from,
        date_to=date_to,
    )

    trace.log_retrieval(sources)

    # Nutze Kompression wenn viele Quellen (ab 10 statt 15 für bessere Qualität)
    use_compression = len(sources) > 10
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
            personen: Liste von Klarnamen (z.B. ["Nora", "Sarah"]).
            orte: Liste von Ortsnamen (z.B. ["München", "Hamburg"]).
            von_datum: Startdatum im Format YYYY-MM-DD (optional).
            bis_datum: Enddatum im Format YYYY-MM-DD (optional).
        """
        logger.info(f"==> Tool Call: search_photos(suchtext='{suchtext[:30]}...', personen={personen}, orte={orte}, von={von_datum}, bis={bis_datum})")
        loc_names = [l.strip() for l in (orte or []) if l.strip()]
        pers_names = [p.strip() for p in (personen or []) if p.strip()]

        res = retrieve_v2(
            query=suchtext,
            user_id=user_id,
            person_names=pers_names,
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
        # Nutze Kompression wenn viele Quellen (ab 10 statt 15)
        use_compression = len(res) > 10
        return _format_sources_for_llm(res, use_compression=use_compression)

    def search_messages(
        suchtext: str = "",
        personen: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
        schluesselwoerter: list[str] | None = None,
    ) -> str:
        """Sucht gezielt in den Textnachrichten und Chatverläufen des Nutzers (WhatsApp/Signal).
        Ideal um Emotionen, Unterhaltungen, spezifische Namen oder Ereignisse herauszufinden.

        Args:
            suchtext: Inhalt der gesuchten Nachrichten (z.B. "Wie geht es dir?", "Treffen").
            personen: Liste von Klarnamen mit denen geschrieben wurde (z.B. ["Sarah", "Marius"]).
            von_datum: Startdatum im Format YYYY-MM-DD (optional).
            bis_datum: Enddatum im Format YYYY-MM-DD (optional).
            schluesselwoerter: Exakte Wörter/Namen die im Text vorkommen MÜSSEN (z.B. ["Jazz", "Schlaganfall"]).
                               Nutze dies für Eigennamen von Personen, Haustieren oder spezifischen Ereignissen,
                               die per Semantic Search nicht gefunden werden könnten.
        """
        logger.info(f"==> Tool Call: search_messages(suchtext='{suchtext[:30]}...', personen={personen}, von={von_datum}, bis={bis_datum}, keywords={schluesselwoerter})")
        pers_names = [p.strip() for p in (personen or []) if p.strip()]

        # Phase 1: Semantic Search (immer)
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

        # Phase 2: Keyword-Suche wenn schluesselwoerter angegeben
        # Ergänzt Ergebnisse die per Similarity NICHT gefunden werden (z.B. Eigennamen)
        if schluesselwoerter:
            from backend.rag.store_es import keyword_search_v2
            kw_results = keyword_search_v2(
                collection_name="messages",
                query=" ".join(schluesselwoerter),
                user_id=user_id,
                n_results=15,
                date_from=von_datum,
                date_to=bis_datum,
            )
            logger.info(f"    Keyword-Search '{schluesselwoerter}': {len(kw_results)} Treffer")
            existing_ids = {s["id"] for s in res}
            for s in kw_results:
                if s["id"] not in existing_ids:
                    res.append(s)
                    existing_ids.add(s["id"])

        existing_ids = {s["id"] for s in sources}
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                existing_ids.add(s["id"])
        # Nutze Kompression wenn viele Quellen (ab 10 statt 15)
        use_compression = len(res) > 10
        return _format_sources_for_llm(res, use_compression=use_compression)

    # Zusammenfassung für User/Prompt
    filter_parts = []
    if person_names:
        filter_parts.append(f"Personen: {', '.join(person_names)}")
    if location_names:
        filter_parts.append(f"Orte: {', '.join(location_names)}")
    if date_from:
        filter_parts.append(f"Ab: {date_from}")
    if date_to:
        filter_parts.append(f"Bis: {date_to}")
    filter_summary = " · ".join(filter_parts)

    filter_note = f"\nErkannte Suchfilter: {filter_summary}" if filter_summary else ""

    user_prompt = (
        f"NUTZERANFRAGE:\n{query}\n\n"
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

    trace.log_prompts(sys_prompt, user_prompt)

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Nur Gemini unterstützt aktuell Tool-Calling über unser Wrapper-Framework
    cfg = get_cfg()
    llm_cfg = cfg.get("llm", {})
    trace.log_provider(llm_cfg.get("provider", ""), llm_cfg.get("model", ""))
    use_tools = [search_photos, search_messages] if llm_cfg.get("provider") == "gemini" else None

    llm_answer = chat(messages, tools=use_tools)
    trace.finish(llm_answer)

    return {
        "query": query,
        "answer": llm_answer,
        "sources": sources,
        "filter_summary": filter_summary,
        "query_id": trace.query_id,
    }

async def answer_v2_stream(
    query: str,
    user_id: str,
    chat_history: list[dict] | None = None,
    person_names: list[str] | None = None,
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

    # NEU: Query-Analyzer für komplexe Anfragen
    try:
        from backend.rag.query_analyzer import analyze_query
        analyzed = analyze_query(query)

        # Sende Query-Analysis als Event
        yield json.dumps({
            "type": "query_analysis",
            "content": {
                "query_type": analyzed.query_type,
                "complexity": analyzed.complexity,
                "sub_queries": analyzed.sub_queries,
                "temporal_fuzzy": analyzed.temporal_fuzzy,
                "entities": analyzed.entities,
                "reasoning": analyzed.reasoning
            }
        }) + "\n\n"

        # Übernehme erkannte Entities
        if analyzed.entities and not person_names:
            person_names = [e for e in analyzed.entities if e[0].isupper()]
        if analyzed.entities and not location_names:
            location_names = analyzed.entities

        logger.info("Query-Analyzer: type=%s, complexity=%s, entities=%s",
                   analyzed.query_type, analyzed.complexity, analyzed.entities)
    except Exception as exc:
        logger.warning("Query-Analyzer fehlgeschlagen (nutze Fallback): %s", exc)

    # Fallback: Parse die Anfrage via LLM, um Orte/Personen zu extrahieren,
    # die das Frontend nicht übergeben hat.
    # Initialisiere location_names und person_names falls nicht übergeben
    location_names = location_names or []
    person_names = person_names or []

    try:
        from backend.rag.query_parser import parse_query
        parsed = parse_query(query)
        if parsed.locations:
            logger.info("Stream-Fallback: LLM-Parser fand Klartext-Orte: %s", parsed.locations)
            location_names = list(location_names) + parsed.locations
        if parsed.persons:
            logger.info("Stream-Fallback: LLM-Parser fand Klartext-Personen: %s", parsed.persons)
            person_names = list(person_names) + parsed.persons
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
        
        # Nutze Kompression für Tool-Results (ab 10 statt 15)
        use_compression = len(res) > 10
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res, use_compression=use_compression)})

    def search_messages(
        suchtext: str = "",
        personen: list[str] | None = None,
        von_datum: str | None = None,
        bis_datum: str | None = None,
        schluesselwoerter: list[str] | None = None,
    ) -> str:
        """Sucht in Textnachrichten (WhatsApp/Signal). Nutze schluesselwoerter für
        Eigennamen wie Haustiere, Personen oder spezifische Ereignisse.

        Args:
            suchtext: Semantischer Suchtext.
            personen: Personen mit denen geschrieben wurde.
            von_datum: Startdatum YYYY-MM-DD (optional).
            bis_datum: Enddatum YYYY-MM-DD (optional).
            schluesselwoerter: Exakte Wörter/Namen die vorkommen MÜSSEN (z.B. ["Jazz"]).
                               Ideal für Eigennamen von Haustieren, seltene Begriffe.
        """
        logger.info(f"==> Stream Tool Call: search_messages({suchtext}, {personen}, {von_datum}, {bis_datum}, kw={schluesselwoerter})")
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

        # Phase 1: Semantic Search
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

        # Phase 2: Keyword-Suche für Eigennamen/spezifische Begriffe
        if schluesselwoerter:
            from backend.rag.store_es import keyword_search_v2
            kw_results = keyword_search_v2(
                collection_name="messages",
                query=" ".join(schluesselwoerter),
                user_id=user_id,
                n_results=15,
                date_from=von_datum,
                date_to=bis_datum,
            )
            logger.info(f"    Stream Keyword-Search '{schluesselwoerter}': {len(kw_results)} Treffer")
            existing_in_res = {s["id"] for s in res}
            for s in kw_results:
                if s["id"] not in existing_in_res:
                    res.append(s)
                    existing_in_res.add(s["id"])

        existing_ids = {s["id"] for s in sources}
        new_sources = []
        for s in res:
            if s["id"] not in existing_ids:
                sources.append(s)
                new_sources.append(s)
                existing_ids.add(s["id"])

        # Nutze Kompression für Tool-Results (ab 10 statt 15)
        use_compression = len(res) > 10
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
                
        # Nutze Kompression für Tool-Results (ab 10 statt 15)
        use_compression = len(res) > 10
        return json.dumps({"new_sources": new_sources, "formatted_context": _format_sources_for_llm(res, use_compression=use_compression)})

    # Nutze Kompression wenn viele Quellen (ab 10 statt 15 für bessere Qualität)
    use_compression = len(sources) > 10
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
        f"(`search_places` sucht in Restaurantbewertungen und gespeicherten Orten). "
        f"WICHTIG: Bei Eigennamen wie Haustieren (z.B. 'Jazz') nutze `search_messages` mit `schluesselwoerter=[\"Jazz\"]` — "
        f"sonst findet die semantische Suche den Namen möglicherweise nicht.\n"
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
