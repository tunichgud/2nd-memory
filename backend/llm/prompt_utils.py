"""
prompt_utils.py – Zentrale Utilities für LLM-Prompts in memosaur.

Wichtig: Diese Funktionen stellen sicher, dass ALLE Prompts konsistent
das aktuelle Datum enthalten, um Temporal Hallucinations zu vermeiden.
"""

from datetime import datetime, timedelta


def get_current_date_header() -> str:
    """Gibt einen formatierten Header mit dem aktuellen Datum zurück.

    Dieser Header MUSS in jedem System-Prompt verwendet werden, der
    zeitliche Berechnungen durchführt oder auf Datumsangaben reagiert.

    Returns:
        Formatierter String mit Datum, Wochentag und relativen Referenzen.

    Beispiel-Output:
        ⚠️ WICHTIG - AKTUELLES DATUM: 10.03.2026 (Dienstag)

        Zeitliche Berechnungen IMMER von diesem Datum aus:
        - "letztes Wochenende" = Samstag 07.03.2026 + Sonntag 08.03.2026
        - "diese Woche" = 09.03.2026 bis 15.03.2026
        - "gestern" = 09.03.2026
        - "vorgestern" = 08.03.2026
        - "letztes Jahr" = 2025
        - "dieses Jahr" = 2026
    """
    now = datetime.now()
    current_date = now.strftime('%d.%m.%Y')
    current_weekday = now.strftime('%A')

    weekday_map = {
        'Monday': 'Montag', 'Tuesday': 'Dienstag', 'Wednesday': 'Mittwoch',
        'Thursday': 'Donnerstag', 'Friday': 'Freitag', 'Saturday': 'Samstag', 'Sunday': 'Sonntag'
    }
    weekday_de = weekday_map.get(current_weekday, current_weekday)

    # Relative Datums-Referenzen berechnen
    last_saturday = now - timedelta(days=now.weekday() + 2)
    last_sunday = now - timedelta(days=now.weekday() + 1)
    week_start = now - timedelta(days=now.weekday())
    week_end = now + timedelta(days=6 - now.weekday())
    yesterday = now - timedelta(days=1)
    day_before_yesterday = now - timedelta(days=2)

    return f"""⚠️ WICHTIG - AKTUELLES DATUM: {current_date} ({weekday_de})

Zeitliche Berechnungen IMMER von diesem Datum aus:
- "letztes Wochenende" = Samstag {last_saturday.strftime('%d.%m.%Y')} + Sonntag {last_sunday.strftime('%d.%m.%Y')}
- "diese Woche" = {week_start.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')}
- "gestern" = {yesterday.strftime('%d.%m.%Y')}
- "vorgestern" = {day_before_yesterday.strftime('%d.%m.%Y')}
- "letztes Jahr" = {now.year - 1}
- "dieses Jahr" = {now.year}"""


def get_current_date_compact() -> str:
    """Gibt eine kompakte Datumsangabe zurück (für kurze Prompts).

    Returns:
        Formatierter String mit Datum und Jahr-Info.

    Beispiel-Output:
        ⚠️ AKTUELLES DATUM: 10.03.2026 (Jahr 2026, Monat 3)
    """
    now = datetime.now()
    return f"""⚠️ AKTUELLES DATUM: {now.strftime('%d.%m.%Y')} (Jahr {now.year}, Monat {now.month})"""


def get_year_context() -> dict:
    """Gibt ein Dict mit Jahr-Kontextinformationen zurück.

    Nützlich für Prompt-Konstruktion mit expliziten Werten.

    Returns:
        Dict mit: current_year, last_year, current_month, current_date
    """
    now = datetime.now()
    return {
        "current_year": now.year,
        "last_year": now.year - 1,
        "current_month": now.month,
        "current_date": now.strftime('%d.%m.%Y'),
        "iso_date": now.strftime('%Y-%m-%d'),
    }
