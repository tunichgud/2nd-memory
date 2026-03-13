"""
temporal_utils.py – Fuzzy Temporal Logic für RAG v3.

Problem:
  User sagt "letztes Jahr", meint aber 2024 (nicht 2025).
  Aktuelles System findet nichts → Frustration.

Lösung:
  Temporal Fuzzy Expansion → Probiere mehrere Zeiträume parallel.

Beispiel:
  expand_temporal_query("letztes Jahr", fuzzy=True)
  → [("2025-01-01", "2025-12-31"),  # letztes Jahr
     ("2024-01-01", "2024-12-31"),  # vorletztes (User-Fehler)
     ("2023-01-01", "2023-12-31")]  # vor 2 Jahren (Sicherheit)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class TemporalRange:
    """Ein Zeitraum mit optionalem Label."""
    date_from: str  # ISO-Format YYYY-MM-DD
    date_to: str    # ISO-Format YYYY-MM-DD
    label: str = "" # z.B. "Letzter Sommer", "Vorletztes Jahr"
    confidence: float = 1.0  # 0.0-1.0 (für Ranking)


# ---------------------------------------------------------------------------
# Temporal Expansion
# ---------------------------------------------------------------------------

def expand_temporal_query(
    query: str,
    fuzzy: bool = False,
    reference_date: Optional[datetime] = None
) -> list[TemporalRange]:
    """
    Expandiert temporale Ausdrücke zu mehreren Zeiträumen.

    Args:
        query: Text mit temporalen Ausdrücken ("letztes Jahr", "Sommer 2024")
        fuzzy: Wenn True, generiere zusätzliche Fallback-Zeiträume (±1 Jahr)
        reference_date: Referenz-Datum (default: heute)

    Returns:
        Liste von TemporalRange, sortiert nach Confidence (höchste zuerst)

    Beispiel:
        expand_temporal_query("letztes Jahr", fuzzy=True)
        → [TemporalRange("2025-01-01", "2025-12-31", "Letztes Jahr", 1.0),
           TemporalRange("2024-01-01", "2024-12-31", "Vorletztes Jahr (Fallback)", 0.7)]
    """
    if reference_date is None:
        reference_date = datetime.now()

    logger.info("Temporal Expansion: '%s' (fuzzy=%s, ref=%s)", query[:50], fuzzy, reference_date.date())

    q_lower = query.lower()

    ranges = []

    # --- Explizite Jahre (z.B. "2024") ---
    year_matches = re.findall(r'\b(20\d{2})\b', query)
    if year_matches:
        for year_str in year_matches:
            year = int(year_str)
            ranges.append(TemporalRange(
                date_from=f"{year}-01-01",
                date_to=f"{year}-12-31",
                label=f"Jahr {year}",
                confidence=1.0
            ))

    # --- Relative Jahresangaben ---
    if "letztes jahr" in q_lower or "voriges jahr" in q_lower:
        last_year = reference_date.year - 1
        ranges.append(TemporalRange(
            date_from=f"{last_year}-01-01",
            date_to=f"{last_year}-12-31",
            label="Letztes Jahr",
            confidence=1.0
        ))

        if fuzzy:
            # Fallback: Vorletztes Jahr (User könnte sich geirrt haben)
            two_years_ago = reference_date.year - 2
            ranges.append(TemporalRange(
                date_from=f"{two_years_ago}-01-01",
                date_to=f"{two_years_ago}-12-31",
                label="Vorletztes Jahr (Fallback)",
                confidence=0.7
            ))

    # --- Jahreszeiten ---
    season_year = None
    for match in re.finditer(r'(sommer|winter|herbst|frühling|frühjahr)\s*(20\d{2})?', q_lower):
        season = match.group(1)
        year_str = match.group(2)
        season_year = int(year_str) if year_str else reference_date.year - 1  # Default: letztes Jahr

        season_ranges = _get_season_ranges(season, season_year)
        ranges.extend(season_ranges)

        if fuzzy and not year_str:
            # Fallback: Auch ein Jahr davor probieren
            fallback_ranges = _get_season_ranges(season, season_year - 1)
            for r in fallback_ranges:
                r.label += " (Fallback -1 Jahr)"
                r.confidence = 0.6
            ranges.extend(fallback_ranges)

    # Spezial: "letzten Sommer" ohne Jahreszahl
    if ("letzten sommer" in q_lower or "letzter sommer" in q_lower) and not season_year:
        last_summer = reference_date.year if reference_date.month >= 6 else reference_date.year - 1
        ranges.append(TemporalRange(
            date_from=f"{last_summer}-06-01",
            date_to=f"{last_summer}-08-31",
            label=f"Letzter Sommer ({last_summer})",
            confidence=1.0
        ))

        if fuzzy:
            ranges.append(TemporalRange(
                date_from=f"{last_summer - 1}-06-01",
                date_to=f"{last_summer - 1}-08-31",
                label=f"Sommer {last_summer - 1} (Fallback)",
                confidence=0.6
            ))

    # --- Relative Zeitangaben (ungenau) ---
    if any(kw in q_lower for kw in ["neulich", "kürzlich", "vor kurzem", "letztens"]):
        # Letzte 30 Tage
        end = reference_date
        start = end - timedelta(days=30)
        ranges.append(TemporalRange(
            date_from=start.strftime('%Y-%m-%d'),
            date_to=end.strftime('%Y-%m-%d'),
            label="Letzte 30 Tage",
            confidence=1.0
        ))

        if fuzzy:
            # Fallback: Letzte 90 Tage
            start_90 = end - timedelta(days=90)
            ranges.append(TemporalRange(
                date_from=start_90.strftime('%Y-%m-%d'),
                date_to=end.strftime('%Y-%m-%d'),
                label="Letzte 90 Tage (Fallback)",
                confidence=0.7
            ))

    if "damals" in q_lower:
        # Sehr ungenau → große Range (letztes Jahr)
        last_year = reference_date.year - 1
        ranges.append(TemporalRange(
            date_from=f"{last_year}-01-01",
            date_to=f"{last_year}-12-31",
            label="Damals (vermutlich letztes Jahr)",
            confidence=0.8
        ))

        if fuzzy:
            # Auch 2 Jahre zurück
            two_years_ago = reference_date.year - 2
            ranges.append(TemporalRange(
                date_from=f"{two_years_ago}-01-01",
                date_to=f"{two_years_ago}-12-31",
                label="Damals (vorletztes Jahr, Fallback)",
                confidence=0.5
            ))

    # --- Sortiere nach Confidence (höchste zuerst) ---
    ranges.sort(key=lambda r: r.confidence, reverse=True)

    logger.info("Temporal Expansion: %d Zeiträume generiert", len(ranges))
    for i, r in enumerate(ranges[:3]):  # Log nur Top-3
        logger.debug("  [%d] %s: %s bis %s (conf=%.2f)", i+1, r.label, r.date_from, r.date_to, r.confidence)

    return ranges


def _get_season_ranges(season: str, year: int) -> list[TemporalRange]:
    """Gibt Zeiträume für eine Jahreszeit zurück."""
    season_map = {
        "sommer": (6, 1, 8, 31, "Sommer"),
        "winter": (12, 1, 2, 28, "Winter"),  # Winter = Dez-Feb
        "herbst": (9, 1, 11, 30, "Herbst"),
        "frühling": (3, 1, 5, 31, "Frühling"),
        "frühjahr": (3, 1, 5, 31, "Frühjahr"),
    }

    if season not in season_map:
        return []

    start_month, start_day, end_month, end_day, label = season_map[season]

    # Winter ist speziell (Dez → Feb nächstes Jahr)
    if season == "winter":
        return [TemporalRange(
            date_from=f"{year}-{start_month:02d}-{start_day:02d}",
            date_to=f"{year + 1}-{end_month:02d}-{end_day:02d}",
            label=f"{label} {year}/{year + 1}",
            confidence=1.0
        )]

    return [TemporalRange(
        date_from=f"{year}-{start_month:02d}-{start_day:02d}",
        date_to=f"{year}-{end_month:02d}-{end_day:02d}",
        label=f"{label} {year}",
        confidence=1.0
    )]


# ---------------------------------------------------------------------------
# Monatsnamen-Parsing
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "januar": 1, "january": 1, "jan": 1,
    "februar": 2, "february": 2, "feb": 2,
    "märz": 3, "march": 3, "mar": 3, "maerz": 3,
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


def parse_month_name(text: str) -> Optional[int]:
    """
    Extrahiert Monatsnummer aus Text (1-12).

    Beispiel:
        parse_month_name("Im August war ich...") → 8
        parse_month_name("Keine Monate hier") → None
    """
    text_lower = text.lower()
    for name, num in _MONTH_MAP.items():
        if name in text_lower:
            return num
    return None


def get_month_range(month: int, year: Optional[int] = None) -> TemporalRange:
    """
    Gibt Zeitraum für einen Monat zurück.

    Args:
        month: Monatsnummer (1-12)
        year: Jahreszahl (default: aktuelles Jahr)

    Returns:
        TemporalRange für den kompletten Monat
    """
    import calendar

    if year is None:
        year = datetime.now().year

    _, last_day = calendar.monthrange(year, month)

    month_names = {
        1: "Januar", 2: "Februar", 3: "März", 4: "April",
        5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
        9: "September", 10: "Oktober", 11: "November", 12: "Dezember"
    }

    return TemporalRange(
        date_from=f"{year}-{month:02d}-01",
        date_to=f"{year}-{month:02d}-{last_day:02d}",
        label=f"{month_names[month]} {year}",
        confidence=1.0
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def format_temporal_ranges(ranges: list[TemporalRange]) -> str:
    """Formatiert Zeiträume für Log-Ausgabe oder User-Feedback."""
    if not ranges:
        return "Keine Zeiträume erkannt"

    lines = []
    for i, r in enumerate(ranges, 1):
        conf_pct = int(r.confidence * 100)
        lines.append(f"{i}. {r.label} ({r.date_from} bis {r.date_to}) [{conf_pct}%]")

    return "\n".join(lines)


def merge_overlapping_ranges(ranges: list[TemporalRange]) -> list[TemporalRange]:
    """
    Merged überlappende Zeiträume (optional, für Optimierung).

    Beispiel:
        [("2024-06-01", "2024-08-31"), ("2024-07-01", "2024-09-30")]
        → [("2024-06-01", "2024-09-30")]
    """
    if not ranges:
        return []

    # Sortiere nach Start-Datum
    sorted_ranges = sorted(ranges, key=lambda r: r.date_from)

    merged = [sorted_ranges[0]]

    for current in sorted_ranges[1:]:
        last = merged[-1]

        # Überlappung?
        if current.date_from <= last.date_to:
            # Merge
            merged[-1] = TemporalRange(
                date_from=min(last.date_from, current.date_from),
                date_to=max(last.date_to, current.date_to),
                label=f"{last.label} + {current.label}",
                confidence=max(last.confidence, current.confidence)
            )
        else:
            merged.append(current)

    return merged
