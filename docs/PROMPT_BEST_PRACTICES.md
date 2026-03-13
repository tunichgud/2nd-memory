# Prompt Engineering Best Practices für 2nd Memory

## 🚨 KRITISCH: Datumsangaben in Prompts

### Problem: Temporal Hallucination

LLMs haben **keine Kenntnis des aktuellen Datums**. Ohne explizite Angabe halluzinieren sie:
- "letztes Jahr" → Falsches Jahr (z.B. 2022 statt 2025)
- "gestern" → Beliebiges Datum
- Relative Zeitangaben werden geraten

### Lösung: Zentrale Utility-Funktion

**IMMER** die zentrale Funktion verwenden, **NIEMALS** manuell berechnen!

```python
from backend.llm.prompt_utils import get_current_date_header, get_current_date_compact

# Für ausführliche Prompts (Agent-Systeme):
def my_system_prompt() -> str:
    return f"""{get_current_date_header()}

    Du bist ein Agent für...
    """

# Für kompakte Prompts (Parser, Analyzer):
def my_compact_prompt() -> str:
    return f"""{get_current_date_compact()}

    Analysiere die Anfrage...
    """
```

### Verfügbare Funktionen

| Funktion | Output | Use Case |
|----------|--------|----------|
| `get_current_date_header()` | Vollständig mit Wochentag + relative Referenzen | Agent System-Prompts (retriever_v2, retriever_v3) |
| `get_current_date_compact()` | Kompakt: Datum + Jahr + Monat | Parser/Analyzer (query_parser, query_analyzer) |
| `get_year_context()` | Dict mit current_year, last_year, etc. | Programmlogik + Prompt-Konstruktion |

### Beispiel-Output

**get_current_date_header():**
```
⚠️ WICHTIG - AKTUELLES DATUM: 10.03.2026 (Dienstag)

Zeitliche Berechnungen IMMER von diesem Datum aus:
- "letztes Wochenende" = Samstag 07.03.2026 + Sonntag 08.03.2026
- "diese Woche" = 09.03.2026 bis 15.03.2026
- "gestern" = 09.03.2026
- "vorgestern" = 08.03.2026
- "letztes Jahr" = 2025
- "dieses Jahr" = 2026
```

**get_current_date_compact():**
```
⚠️ AKTUELLES DATUM: 10.03.2026 (Jahr 2026, Monat 3)
```

---

## ✅ Checklist für neue Prompts

Bevor du einen neuen System-Prompt erstellst:

- [ ] Nutzt der Prompt temporale Daten? (Datum, Jahr, relative Zeitangaben?)
- [ ] Wird `get_current_date_header()` oder `get_current_date_compact()` verwendet?
- [ ] Steht die Datumsangabe **ganz oben** im Prompt? (⚠️ WICHTIG - AKTUELLES DATUM:...)
- [ ] Nutzt der Prompt relative Zeitangaben? → Dann auch "letztes Jahr", "dieses Jahr" explizit angeben!

---

## 🔍 Migration-Guide

### Vorher (❌ NICHT MEHR VERWENDEN):

```python
def _get_system_prompt() -> str:
    now = datetime.now()
    current_date = now.strftime('%d.%m.%Y')

    return f"""Aktuelles Datum: {current_date}

    Du bist ein Agent...
    """
```

**Problem:**
- Duplikation der Datums-Logik
- Inkonsistente Formatierung
- Manuelle Berechnung von relativen Referenzen fehleranfällig

### Nachher (✅ BEST PRACTICE):

```python
def _get_system_prompt() -> str:
    from backend.llm.prompt_utils import get_current_date_header

    return f"""{get_current_date_header()}

    Du bist ein Agent...
    """
```

**Vorteile:**
- Zentrale Quelle der Wahrheit
- Konsistente Formatierung
- Automatische Berechnung von relativen Referenzen
- Leicht zu testen und zu warten

---

## 🧪 Testing

```python
# Test prompt generation
from backend.llm.prompt_utils import get_current_date_header

prompt = get_current_date_header()
print(prompt)

# Erwartung: Aktuelles Datum ist korrekt
# Erwartung: "letztes Jahr" = datetime.now().year - 1
```

---

## 📝 Affected Files (bereits migriert)

- ✅ `backend/rag/retriever_v2.py` → `_get_system_prompt()`
- ✅ `backend/rag/retriever_v3.py` → `_get_system_prompt_v3()`
- ✅ `backend/rag/query_parser.py` → `_get_parse_system_prompt()`
- ✅ `backend/rag/query_analyzer.py` → `_get_analyzer_prompt()`

---

## 🚀 Zukünftige Erweiterungen

Wenn neue Prompt-Funktionen hinzugefügt werden:

1. **Prüfen:** Braucht der Prompt Datum-Kontext?
2. **Importieren:** `from backend.llm.prompt_utils import get_current_date_header`
3. **Verwenden:** Am Anfang des Prompts platzieren
4. **Dokumentieren:** Diese Datei aktualisieren unter "Affected Files"

---

## ⚠️ WICHTIG: Code Review Checklist

Bei Pull Requests mit neuen/geänderten Prompts:

- [ ] Keine hardcoded Datums-Berechnungen (datetime.now() direkt im Prompt)
- [ ] Nutzung von `prompt_utils.py` für Datum-Kontext
- [ ] Datumsangabe steht am Anfang des Prompts (hohe Salienz für LLM)
- [ ] Bei relativen Zeitangaben: Explizite Referenzen ("letztes Jahr = 2025")

---

## 📚 Weitere Best Practices

### 1. Prompt-Struktur

```
⚠️ DATUM (höchste Priorität)

Rolle & Aufgabe

Beispiele (Few-Shot Learning)

Regeln & Constraints

Output-Format
```

### 2. Emoji-Nutzung

- ⚠️ für kritische Informationen (Datum, Warnungen)
- 🎯 für Hauptziele/Fokus
- ✅ für Best Practices
- ❌ für Anti-Patterns

### 3. Explizite Berechnungen zeigen

**Schlecht:**
```
"Rechne relative Zeitangaben basierend auf dem aktuellen Datum."
```

**Gut:**
```
- "letztes Jahr" = 2025 (NICHT 2026!)
- "August letzten Jahres" = August 2025 → date_from="2025-08-01"
```

---

**Zuletzt aktualisiert:** 2026-03-10
**Version:** 1.0
**Autor:** 2nd Memory Team
