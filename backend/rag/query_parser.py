"""
query_parser.py – LLM-basierter Query-Parser für memosaur.

Extrahiert strukturierte Filter aus natürlichsprachigen Anfragen:
  - Personennamen
  - Datum / Zeitraum
  - Ortsnamen
  - Relevante Collections
  - ChromaDB where-Filter

Beispiel:
  "Wo war ich im August mit Nora?"
  → ParsedQuery(
      persons=["Nora"],
      date_from="2025-08-01", date_to="2025-08-31",
      relevant_collections=["photos", "messages"],
      metadata_filters={"photos": {"$and": [{"persons": ...}, {"date_ts": ...}]}}
    )
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Aktuelles Jahr als Fallback
_CURRENT_YEAR = datetime.now().year

# Monatsnamen → Nummer (deutsch + englisch)
_MONTH_MAP: dict[str, int] = {
    "januar": 1, "january": 1, "jan": 1,
    "februar": 2, "february": 2, "feb": 2,
    "märz": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "october": 10, "oct": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "december": 12, "dec": 12, "dez": 12,
}

# Systempr0mpt für Query-Parsing
_PARSE_SYSTEM = """Du bist ein Query-Parser für ein persönliches Gedächtnis-System.

Analysiere die Anfrage und extrahiere strukturierte Informationen als JSON.
Antworte NUR mit gültigem JSON, ohne Erklärungen oder Markdown-Blöcke.

Verfügbare Collections:
- "photos": Fotos mit GPS, Datum, Personen (persons-Feld: kommasepariert)
- "reviews": Google Maps Bewertungen von Restaurants/Orten
- "saved_places": Gespeicherte Google Maps Orte
- "messages": WhatsApp/Signal Nachrichten (Personen im Text erwähnt)

JSON-Schema:
{
  "persons": [],           // Genannte Personennamen, exakt wie geschrieben
  "locations": [],         // Genannte Ortsnamen oder Regionen
  "month": null,           // Monatsnummer 1-12 oder null
  "year": null,            // Jahreszahl oder null
  "date_from": null,       // ISO-Datum YYYY-MM-DD oder null
  "date_to": null,         // ISO-Datum YYYY-MM-DD oder null
  "topics": [],            // Themen: "restaurant", "location", "activity", "person"
  "relevant_collections": [] // Subset von ["photos","reviews","saved_places","messages"]
}

Regeln:
- persons: Nur echte Personennamen extrahieren, keine Pronomen
- relevant_collections: photos+messages wenn Personen gefragt; reviews+saved_places wenn Orte/Restaurants gefragt
- Bei Monatsnennung ohne Jahr: nimm das aktuellste Jahr mit Daten (""" + str(_CURRENT_YEAR) + """)
- date_from/date_to: Berechne den exakten Zeitraum aus Monat/Jahr"""


@dataclass
class ParsedQuery:
    """Strukturierte Darstellung einer natürlichsprachigen Anfrage."""
    raw: str = ""
    persons: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    month: int | None = None
    year: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    topics: list[str] = field(default_factory=list)
    relevant_collections: list[str] = field(default_factory=list)
    # Berechnete ChromaDB where-Filter pro Collection
    metadata_filters: dict[str, dict | None] = field(default_factory=dict)
    # Ob der Parser erfolgreich war
    parsed_ok: bool = False


def parse_query(query: str) -> ParsedQuery:
    """Extrahiert strukturierte Filter aus einer natürlichsprachigen Anfrage.

    Versucht zuerst regelbasiert (schnell, kein LLM-Aufruf nötig für einfache
    Abfragen), fällt dann auf LLM zurück für komplexere Anfragen.
    """
    pq = ParsedQuery(raw=query)

    # Schritt 1: Regelbasierte Extraktion (immer ausführen als Basis)
    _extract_rules(pq)

    # Schritt 2: LLM-Verbesserung
    try:
        _extract_llm(pq)
        pq.parsed_ok = True
    except Exception as exc:
        logger.warning("LLM Query-Parsing fehlgeschlagen, nutze Regelbasiert: %s", exc)
        pq.parsed_ok = bool(pq.persons or pq.date_from or pq.locations)

    # Schritt 3: Metadaten-Filter ableiten
    _build_metadata_filters(pq)

    logger.info(
        "Query geparst: persons=%s date=%s..%s collections=%s",
        pq.persons, pq.date_from, pq.date_to, pq.relevant_collections,
    )
    return pq


def _extract_rules(pq: ParsedQuery) -> None:
    """Schnelle regelbasierte Extraktion ohne LLM."""
    text = pq.raw.lower()

    # Monat erkennen
    for name, num in _MONTH_MAP.items():
        if name in text:
            pq.month = num
            break

    # Jahr erkennen (4-stellig)
    year_match = re.search(r"\b(20\d{2})\b", pq.raw)
    if year_match:
        pq.year = int(year_match.group(1))

    # Datum-Range berechnen
    if pq.month:
        year = pq.year or _CURRENT_YEAR
        _set_month_range(pq, year, pq.month)

    # Collections nach Keywords vorbelegen
    person_keywords = ["mit ", "wer ", "nora", "sarah", "joshua", "personen"]
    location_keywords = ["wo ", "restaurant", "kneipe", "ort", "reise", "urlaub", "gegessen"]
    message_keywords = ["nachrichten", "chat", "whatsapp", "signal", "geschrieben", "sagt"]

    has_person = any(kw in text for kw in person_keywords)
    has_location = any(kw in text for kw in location_keywords)
    has_message = any(kw in text for kw in message_keywords)

    cols = []
    if has_person or has_message:
        cols += ["photos", "messages"]
    if has_location:
        cols += ["photos", "reviews", "saved_places"]
    if not cols:
        cols = ["photos", "reviews", "saved_places", "messages"]

    pq.relevant_collections = list(dict.fromkeys(cols))  # dedupliziert, Reihenfolge erhalten


def _extract_llm(pq: ParsedQuery) -> None:
    """LLM-basierte Verbesserung der regelbasierten Extraktion."""
    from backend.llm.connector import chat

    messages = [
        {"role": "system", "content": _PARSE_SYSTEM},
        {"role": "user", "content": pq.raw},
    ]

    raw_response = chat(messages)

    # JSON aus Antwort extrahieren (auch wenn Markdown-Blöcke drumherum sind)
    json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
    if not json_match:
        raise ValueError(f"Kein JSON in LLM-Antwort: {raw_response[:200]}")

    data = json.loads(json_match.group())

    # Ergebnisse übernehmen (LLM überschreibt Regelbasiert)
    if data.get("persons"):
        pq.persons = [p.strip() for p in data["persons"] if p.strip()]

    if data.get("locations"):
        pq.locations = [l.strip() for l in data["locations"] if l.strip()]

    if data.get("month") and not pq.month:
        pq.month = int(data["month"])

    if data.get("year"):
        pq.year = int(data["year"])

    if data.get("date_from"):
        pq.date_from = data["date_from"]
    if data.get("date_to"):
        pq.date_to = data["date_to"]

    # Datum aus Monat/Jahr neu berechnen wenn nötig
    if pq.month and not pq.date_from:
        year = pq.year or _CURRENT_YEAR
        _set_month_range(pq, year, pq.month)

    if data.get("topics"):
        pq.topics = data["topics"]

    if data.get("relevant_collections"):
        # LLM-Collections mit regelbasierten mergen
        llm_cols = data["relevant_collections"]
        # Vereinigung, LLM-Reihenfolge bevorzugt
        merged = list(dict.fromkeys(llm_cols + pq.relevant_collections))
        pq.relevant_collections = merged


def _set_month_range(pq: ParsedQuery, year: int, month: int) -> None:
    """Setzt date_from und date_to für einen kompletten Monat."""
    import calendar
    _, last_day = calendar.monthrange(year, month)
    pq.date_from = f"{year}-{month:02d}-01"
    pq.date_to = f"{year}-{month:02d}-{last_day:02d}"


def _person_field(name: str) -> str:
    """Konvertiert einen Personennamen in ein ChromaDB-Boolean-Metadatenfeld.

    Beispiel: "Joshua Bacher" → "has_joshua", "Nora" → "has_nora"
    """
    first = name.split()[0].lower()
    for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        first = first.replace(src, dst)
    return f"has_{first}"


def _build_metadata_filters(pq: ParsedQuery) -> None:
    """Leitet ChromaDB where-Filter aus dem ParsedQuery ab.

    Personenfilter verwenden Boolean-Felder (has_nora, has_sarah etc.)
    da ChromaDB kein Substring-Matching auf Strings unterstützt.
    Beide Collections (photos + messages) haben diese Felder.
    """
    filters: dict[str, dict | None] = {}

    for col in pq.relevant_collections:
        conditions = []

        # Datumsfilter
        if pq.date_from:
            try:
                ts = int(datetime.fromisoformat(pq.date_from).replace(tzinfo=timezone.utc).timestamp())
                conditions.append({"date_ts": {"$gte": ts}})
            except ValueError:
                pass

        if pq.date_to:
            try:
                ts = int(datetime.fromisoformat(pq.date_to + "T23:59:59").replace(tzinfo=timezone.utc).timestamp())
                conditions.append({"date_ts": {"$lte": ts}})
            except ValueError:
                pass

        # Personenfilter via Boolean-Felder – für photos und messages
        if pq.persons and col in ("photos", "messages"):
            for person in pq.persons:
                field = _person_field(person)
                conditions.append({field: {"$eq": True}})

        # Filter zusammenbauen
        if not conditions:
            filters[col] = None
        elif len(conditions) == 1:
            filters[col] = conditions[0]
        else:
            filters[col] = {"$and": conditions}

    pq.metadata_filters = filters


def summarize(pq: ParsedQuery) -> str:
    """Erzeugt eine kurze menschenlesbare Zusammenfassung der erkannten Filter."""
    parts = []
    if pq.persons:
        parts.append(f"Personen: {', '.join(pq.persons)}")
    if pq.date_from and pq.date_to:
        # Schöne Monatsangabe wenn voller Monat
        try:
            df = datetime.fromisoformat(pq.date_from)
            dt = datetime.fromisoformat(pq.date_to)
            import calendar
            _, last = calendar.monthrange(df.year, df.month)
            if df.day == 1 and dt.day == last and df.month == dt.month:
                month_name = df.strftime("%B %Y")
                parts.append(f"Zeitraum: {month_name}")
            else:
                parts.append(f"Zeitraum: {df.strftime('%d.%m.%Y')} – {dt.strftime('%d.%m.%Y')}")
        except ValueError:
            parts.append(f"Zeitraum: {pq.date_from} – {pq.date_to}")
    elif pq.date_from:
        parts.append(f"Ab: {pq.date_from}")
    if pq.locations:
        parts.append(f"Orte: {', '.join(pq.locations)}")
    return " · ".join(parts) if parts else ""
