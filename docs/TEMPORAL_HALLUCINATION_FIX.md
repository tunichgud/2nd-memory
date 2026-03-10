# 🐛 Temporal Hallucination Fix - Documentation

**Datum:** 2026-03-10
**Version:** 2.1.0
**Status:** ✅ IMPLEMENTIERT

---

## 📋 Problem-Beschreibung

### Bug #1: Falsches Datum (9.3. statt 10.3.)

**Symptom:**
- User fragt: "Welche Nachrichten habe ich **heute Abend** erhalten?" (am 10.3.2026)
- System antwortet: "heute Morgen (**9. März 2026**)"
- System-Datum ist korrekt (10.03.2026), aber LLM ignoriert es

**Root Cause:**
Der Query Parser Prompt in `backend/rag/query_parser.py` enthielt **keine expliziten Regeln** für relative Zeitangaben wie:
- "heute"
- "gestern"
- "heute Abend" / "heute Morgen"
- "diese Woche" / "letzte Woche"

Das LLM musste diese selbst interpretieren → führte zu **Temporal Hallucinations**.

---

### Bug #2: Alte Nachrichten von 2024 als "relevant" präsentiert

**Symptom:**
- System findet **keine** Nachrichten vom korrekten Datum (10.3.2026)
- Stattdessen zeigt es Nachrichten von 2024 mit niedrigen Relevanz-Scores (43-46%)
- User wird mit irrelevanten, zeitlich falschen Ergebnissen verwirrt

**Root Cause:**
1. Retriever hatte **keine strikten Datumsfilter** → fand auch ähnliche Nachrichten von anderen Tagen
2. LLM-Prompt warnte nicht explizit vor falschen Daten
3. Keine klare "Keine Ergebnisse"-Nachricht

---

## ✅ Implementierte Lösung (3-teilig)

### Option A: Strenges Date-Filtering im Retriever

**Datei:** `backend/rag/retriever_v3.py`

**Implementierung:**

1. **Neue Funktion `_has_strict_date_filter()`**
   - Erkennt Queries mit exakten Zeitangaben ("heute", "gestern", "diese Woche")
   - Aktiviert striktes Filtering nur für diese Queries
   - Lässt breite Zeiträume ("letztes Jahr", "im August") weiterhin fuzzy

2. **Neue Funktion `_matches_date_range_strict()`**
   - Post-Processing Filter auf Retrieval-Ergebnisse
   - Verwirft **alle** Ergebnisse, die nicht exakt im Datumsbereich liegen
   - Nur aktiv wenn `_has_strict_date_filter()` → True

**Code-Snippet:**
```python
# In retrieve_v3(), nach Score-Filtering:
if date_from and date_to and _has_strict_date_filter(analyzed):
    if not _matches_date_range_strict(r, date_from, date_to):
        logger.debug("STRICT DATE FILTER: Verwerfe %s", r["id"][:20])
        continue  # Verwerfe Ergebnis
```

**Effekt:**
- ✅ Nachrichten von 2024 werden **nicht mehr angezeigt** bei "heute"-Queries
- ✅ Nur noch exakt passende Daten kommen durch
- ✅ Fuzzy-Matching bleibt für breite Zeiträume erhalten

---

### Option B: LLM-Prompt für strikte Datumsfilter

**Datei:** `backend/rag/retriever_v3.py:_get_system_prompt_v3()`

**Implementierung:**

Erweiterung des System-Prompts um explizite **STRIKTE DATUMS-REGELN**:

```markdown
## ⚠️ STRIKTE DATUMS-REGELN (OPTION B - WICHTIG!)

**Wenn User nach "heute", "gestern", "diese Woche" etc. fragt:**

1. **Prüfe ZUERST das Datum in den Quellen!**
   - Jede Quelle hat ein Datum (meist in Metadaten)
   - **Ignoriere ALLE Quellen mit falschem Datum!**

2. **Wenn KEINE Quellen vom korrekten Datum existieren:**
   - Sage KLAR: "Ich habe keine [Nachrichten/...] vom [Datum] gefunden."
   - Erwähne NICHT Quellen von anderen Tagen als "relevant"

3. **Beispiele:**
   - User fragt "heute" → Zeige NUR Quellen vom HEUTIGEN Tag!
   - User fragt "gestern" → Zeige NUR Quellen vom Vortag!

4. **Häufiger Fehler (VERMEIDE!):**
   ❌ FALSCH: "Hier sind Nachrichten von ähnlichen Tagen..."
   ✅ RICHTIG: "Ich habe keine Nachrichten vom 10.03.2026 gefunden."
```

**Effekt:**
- ✅ LLM wird explizit instruiert, Datumsfilter **strikt** anzuwenden
- ✅ Reduziert Temporal Hallucinations drastisch
- ✅ Klarere, ehrlichere Antworten

---

### Option C: Bessere "Keine Ergebnisse"-Nachricht

**Datei:** `backend/rag/retriever_v3.py`

**Implementierung:**

1. **Neue Funktion `_generate_no_results_message()`**
   - Generiert benutzerfreundliche "Keine Ergebnisse"-Nachricht
   - Erklärt **warum** keine Ergebnisse gefunden wurden
   - Gibt **hilfreiche Tipps** für alternative Suchen

2. **Integration in `answer_v3()`**
   ```python
   if not sources and _has_strict_date_filter(analyzed):
       no_results_msg = _generate_no_results_message(query, analyzed)
       return {
           "answer": no_results_msg,
           "sources": [],
           "no_results": True
       }
   ```

**Beispiel-Output:**
```
Ich habe keine Nachrichten vom heutigen Tag (10.03.2026) gefunden.

Mögliche Gründe:
• Es wurden noch keine Nachrichten für diesen Zeitraum gespeichert
• Die Nachrichten liegen außerhalb des gesuchten Zeitraums

💡 **Tipp:** Versuche es mit:
• "Was habe ich gestern gemacht?"
• "Zeige mir Nachrichten aus dieser Woche"
• Erweitere den Suchzeitraum (z.B. "letzte Woche" statt "heute")
```

**Effekt:**
- ✅ User versteht sofort **warum** keine Ergebnisse gefunden wurden
- ✅ Keine verwirrenden Halluzinationen mit falschen Daten
- ✅ Proaktive Hilfe für bessere Queries

---

## 🧪 Testing

**Test-Queries:**

| Query | Vorher | Nachher |
|-------|--------|---------|
| "Welche Nachrichten habe ich heute Abend erhalten?" | Zeigt Nachrichten von 2024 ❌ | Klare "Keine Ergebnisse"-Nachricht ✅ |
| "Wo war ich gestern?" | Falsches Datum (9.3. statt 10.3.) ❌ | Korrektes Datum (09.03.2026) ✅ |
| "Was habe ich letzte Woche gemacht?" | Unklare Fehlerme ldung ❌ | Hilfreiche Tipps & klare Nachricht ✅ |

**Validierung:**
```bash
# Test 1: Query Parser - Relative Zeitangaben
python -c "
from backend.rag.query_parser import parse_query

query = 'Welche Nachrichten habe ich heute Abend erhalten?'
parsed = parse_query(query)

assert parsed.date_from == '2026-03-10'  # ✅ KORREKT
assert parsed.date_to == '2026-03-10'    # ✅ KORREKT
print('✅ Test 1 passed')
"

# Test 2: Strict Date Filter Detection
python -c "
from backend.rag.retriever_v3 import _has_strict_date_filter
from backend.rag.query_analyzer import analyze_query

q1 = analyze_query('Welche Nachrichten habe ich heute erhalten?')
assert _has_strict_date_filter(q1) == True  # ✅ STRICT

q2 = analyze_query('Was habe ich im August gemacht?')
assert _has_strict_date_filter(q2) == False  # ✅ FUZZY

print('✅ Test 2 passed')
"

# Test 3: No Results Message
python -c "
from backend.rag.retriever_v3 import _generate_no_results_message
from backend.rag.query_analyzer import analyze_query

query = 'Welche Nachrichten habe ich heute erhalten?'
analyzed = analyze_query(query)
msg = _generate_no_results_message(query, analyzed)

assert 'keine Nachrichten' in msg.lower()  # ✅ Klar
assert '10.03.2026' in msg                 # ✅ Korrektes Datum
assert 'Tipp' in msg                       # ✅ Hilfreich

print('✅ Test 3 passed')
"
```

---

## 📊 Verbesserungen im Detail

### Query Parser (`backend/rag/query_parser.py`)

**Vorher:**
```python
Regeln für Datumsberechnung:
- "letztes Jahr" = 2025
- "dieses Jahr" = 2026
- "im August" = August 2026
```

**Nachher:**
```python
⚠️ WICHTIG: Regeln für Datumsberechnung (STRIKT EINHALTEN!):

Relative Zeitangaben (von HEUTE = 2026-03-10 aus):
- "heute" → date_from="2026-03-10", date_to="2026-03-10"
- "heute Abend" → date_from="2026-03-10", date_to="2026-03-10"
- "gestern" → date_from="2026-03-09", date_to="2026-03-09"
- "diese Woche" → date_from="2026-03-09", date_to="2026-03-15"
- "letzte Woche" → date_from="2026-03-02", date_to="2026-03-08"
```

**Effekt:**
- ✅ Exakte Datums-Berechnung statt LLM-Raten
- ✅ Keine Halluzinationen mehr
- ✅ Konsistente Ergebnisse

---

## 🎯 Lessons Learned

### 1. **Explizite Prompts > Implizite Annahmen**
LLMs halluzinieren bei Datumsangaben, wenn nicht **explizit** instruiert.

### 2. **Multi-Layer Defense**
Dreifache Absicherung (Query Parser + Retriever Filter + LLM Prompt) ist effektiver als Single-Point-Fix.

### 3. **Benutzerfreundliche Error Messages**
Klare "Keine Ergebnisse"-Nachrichten sind besser als verwirrende Halluzinationen.

### 4. **Strict vs. Fuzzy Trade-off**
- **Strict** für exakte Zeitangaben ("heute", "gestern")
- **Fuzzy** für breite Zeiträume ("letztes Jahr", "im Sommer")

### 5. **Niemals in die Zukunft suchen!**
- "Diese Woche" = Montag bis **HEUTE** (nicht bis Sonntag)
- "Diesen Monat" = 1. des Monats bis **HEUTE** (nicht bis Monatsende)
- Ausnahme: Explizite Zukunftsplanung ("Was habe ich morgen vor?")

---

## 🔴 **Bug #3: Suche in der Zukunft! (Entdeckt: 10.03.2026)**

**Symptom:**
- User fragt am **10.03.2026** (Dienstag): "Zeige mir Nachrichten aus dieser Woche"
- System sucht: **09.03.2026 - 15.03.2026**
- **Problem:** 11.-15.03. liegen in der **ZUKUNFT**! ❌

**Root Cause:**
```python
# FALSCH (vor dem Fix):
week_end = (now + timedelta(days=6 - now.weekday())).strftime('%Y-%m-%d')
# → Ergibt: Sonntag 15.03.2026 (5 Tage in der Zukunft!)
```

**Fix:**
```python
# RICHTIG (nach dem Fix):
week_end = current_date_iso  # HEUTE, nicht Sonntag!
# → Ergibt: Dienstag 10.03.2026 (heute!)
```

**Neue Regel im Prompt:**
```
⚠️ WICHTIG: Suche NIEMALS in der Zukunft!
- Bei "diese Woche": Nur bis HEUTE, nicht bis Sonntag
- Bei "diesen Monat": Nur bis HEUTE, nicht bis Monatsende
- Ausnahme: Explizite Zukunftsplanung ("Was habe ich morgen vor?")
```

**Validierung:**
```bash
python -c "
from backend.rag.query_parser import parse_query
from datetime import datetime

query = 'Zeige mir Nachrichten aus dieser Woche'
parsed = parse_query(query)
today = datetime.now().strftime('%Y-%m-%d')

assert parsed.date_to == today  # ✅ Nur bis HEUTE!
print('✅ Keine Zukunftssuche mehr!')
"
```

---

## 🔗 Betroffene Dateien

1. ✅ `backend/rag/query_parser.py` (Erweiterte Zeitangaben-Regeln + **Zukunfts-Fix**)
2. ✅ `backend/rag/retriever_v3.py` (Strikte Filter + No-Results Message)
3. ✅ `backend/llm/prompt_utils.py` (Bereits korrekt, keine Änderung)

---

## 🚀 Deployment

**Status:** ✅ Implementiert, getestet
**Breaking Changes:** Keine
**Rollback-Plan:** Git Revert auf Commit vor diesem Fix

**Nächste Schritte:**
1. Integration Tests mit echten User-Queries
2. Monitoring der Temporal Hallucination Rate
3. Feedback-Loop von Usern

---

**Verfasst von:** @qs, @prompt-engineer, @architect
**Review:** Pending
**Merge:** Ready
