# QS Test Plan: Real-Time Denkprozess Streaming

**Feature:** Real-Time Streaming mit LLM-basiertem Temporal Parsing
**Datum:** 2026-03-10
**Assignee:** @qs
**Status:** Ready for Testing

---

## 🎯 Test-Ziele

1. **Real-Time Streaming:** Events werden live gestreamt (nicht gebuffert)
2. **Temporal Parsing:** LLM erkennt "im August letzten Jahres" korrekt
3. **Retrieval Quality:** München-Daten werden gefunden (falls vorhanden)
4. **UX:** User sieht Fortschritt während der Verarbeitung

---

## 🔧 Setup

### 1. Server starten
```bash
cd /home/bacher/prj/mabrains/memosaur
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend öffnen
```
http://localhost:8000/
```

### 3. Debug-Logs aktivieren (optional)
**Backend:**
```bash
# Terminal: Logs werden automatisch angezeigt
# Grep für relevante Zeilen:
grep "Using LLM-parsed temporal filter" logs/...
```

**Frontend:**
```javascript
// Browser Console:
localStorage.setItem('DEBUG', 'true')
// Reload page
```

---

## 📋 Test Cases

### Test 1: Real-Time Streaming (Kritisch!)

**Ziel:** Events werden WÄHREND der Verarbeitung gestreamt (nicht alle am Ende)

**Steps:**
1. Öffne Browser DevTools → Network Tab
2. Query eingeben: `Wo war ich im August letzten Jahres?`
3. Beobachte Timeline im Chat

**Erwartetes Verhalten:**
```
0.0s: User sendet Query
      ↓
0.2s: 🧠 Query-Analyse erscheint
      ↓
0.3s: 💭 Erweitere Suche... erscheint
      ↓
0.4s: 🔍 Retrieval läuft... (Spinner ⚙️)
      ↓
1.5s: 🔍 Retrieval abgeschlossen (✓)
      ↓
1.6s: 💭 Komprimiere Quellen...
      ↓
4.0s: 📝 Antwort streamt (char-by-char)
      ↓
6.0s: 📚 Quellen erscheinen
```

**Pass Criteria:**
- ✅ Mindestens 3 Events erscheinen BEVOR die Antwort fertig ist
- ✅ Retrieval-Event zeigt Spinner (⚙️) während es läuft
- ✅ Spinner wird durch ✓ ersetzt wenn fertig
- ✅ Total Time: 5-8 Sekunden
- ✅ First Event erscheint in <500ms

**Fail Criteria:**
- ❌ Alle Events erscheinen gleichzeitig am Ende
- ❌ Lange Pause (>3s) zwischen Events
- ❌ Kein Spinner (nur statisches Icon)

---

### Test 2: LLM-basiertes Temporal Parsing

**Ziel:** Query "im August letzten Jahres" wird korrekt als `2025-08-01` bis `2025-08-31` erkannt

**Steps:**
1. Query: `Wo war ich im August letzten Jahres?`
2. Warte auf Antwort
3. Prüfe Backend-Logs

**Backend Logs prüfen:**
```bash
grep "Using LLM-parsed temporal filter" logs/...
# Erwarteter Output:
# Using LLM-parsed temporal filter: 2025-08-01 to 2025-08-31
```

**Frontend prüfen:**
```
Klicke "▼ Denkprozess" auf um Query-Analyse zu sehen:

🧠 Query-Analyse
   Typ: Zeitliche Ableitung
   Komplexität: medium
   Datum: 2025-08-01 bis 2025-08-31  ← MUSS angezeigt werden!
```

**Pass Criteria:**
- ✅ `date_from: "2025-08-01"`
- ✅ `date_to: "2025-08-31"`
- ✅ Keine Warnung "0 Zeiträume generiert"
- ✅ Kein Fallback aktiviert

**Fail Criteria:**
- ❌ `date_from: null` oder falsche Daten
- ❌ Log zeigt "Temporal Expansion: 0 Zeiträume generiert"
- ❌ Log zeigt "aktiviere Fallback-Strategien"

---

### Test 3: Retrieval Quality (München-Daten)

**Ziel:** Wenn München-Daten aus August 2025 existieren, werden sie gefunden

**Voraussetzung:** Prüfe ob München-Daten existieren:
```bash
# In Backend Console oder Notebook:
from backend.rag.store_v2 import query_collection_v2
from backend.rag.embedder import embed_single

embedding = embed_single("München August 2025")
results = query_collection_v2(
    collection_name="photos",
    query_embeddings=[embedding],
    n_results=5,
    user_id="<USER_ID>",
    where={
        "$and": [
            {"date_ts": {"$gte": 1722470400}},  # 2025-08-01
            {"date_ts": {"$lte": 1725148799}}   # 2025-08-31
        ]
    }
)
print(f"Gefunden: {len(results['ids'][0])} Dokumente")
```

**Steps:**
1. Query: `Wo war ich im August letzten Jahres?`
2. Prüfe Antwort

**Pass Criteria (wenn München-Daten existieren):**
- ✅ Antwort erwähnt "München" oder konkrete Orte
- ✅ Retrieval zeigt >0 Quellen
- ✅ Top Score >0.5
- ✅ Quellen-Cards zeigen München-Fotos/Messages

**Pass Criteria (wenn KEINE München-Daten existieren):**
- ✅ Antwort: "Ich habe keine Informationen vom August 2025"
- ✅ Retrieval zeigt 0 Quellen
- ✅ Keine Halluzination (z.B. "Du warst in Berlin" wenn keine Daten)

**Fail Criteria:**
- ❌ Antwort halluziniert Daten ("Du warst in X" ohne Quellen)
- ❌ Retrieval findet Daten aus ANDEREN Monaten
- ❌ Antwort erwähnt "keine Daten" obwohl Quellen vorhanden

---

### Test 4: Edge Cases

#### 4.1 Andere Temporal-Ausdrücke

**Queries:**
- `Was habe ich letztes Wochenende gemacht?`
- `Zeige mir Fotos von gestern`
- `Wo war ich im Sommer 2024?`

**Verify:**
- ✅ date_from/date_to werden korrekt berechnet
- ✅ Relative Daten (gestern, letztes Wochenende) funktionieren
- ✅ Jahreszeiten (Sommer 2024) funktionieren

#### 4.2 Queries OHNE Datum

**Query:** `Zeige mir Fotos mit Nora`

**Verify:**
- ✅ date_from/date_to sind null
- ✅ Keine temporalen Filter
- ✅ Suche läuft über alle Zeiträume

#### 4.3 Fehlerfall: Server Offline

**Setup:** Stoppe Ollama oder Gemini (je nach Config)

**Query:** Beliebige Query

**Verify:**
- ✅ Error-Event erscheint
- ✅ Fehlermeldung ist benutzerfreundlich
- ✅ Kein Crash/White Screen

---

## 📊 Test Report Template

```markdown
# QS Test Report: Real-Time Streaming

**Tester:** @qs
**Datum:** YYYY-MM-DD
**Branch:** main
**Commit:** <git commit hash>

## Test 1: Real-Time Streaming
- [ ] Pass / [ ] Fail
- Beobachtung:
- Screenshots:

## Test 2: LLM Temporal Parsing
- [ ] Pass / [ ] Fail
- date_from:
- date_to:
- Logs:

## Test 3: Retrieval Quality
- [ ] Pass / [ ] Fail
- Quellen gefunden:
- Top Score:
- Antwort korrekt:

## Test 4: Edge Cases
- 4.1: [ ] Pass / [ ] Fail
- 4.2: [ ] Pass / [ ] Fail
- 4.3: [ ] Pass / [ ] Fail

## Bugs gefunden
1.
2.

## Empfehlung
- [ ] Ready for Production
- [ ] Needs Fixes (siehe Bugs)
- [ ] Needs Re-Design
```

---

## 🐛 Known Issues (vor Testing)

1. **retrieve_v2 vs retrieve_v3:**
   - Aktuell nutzen wir `retrieve_v2` als Workaround
   - TODO: `retrieve_v3` sollte auch `date_from`/`date_to` unterstützen

2. **Synonym Expansion läuft 2x:**
   - Einmal in `answer_v3_stream`
   - Einmal in `retrieve_v2`
   - Performance-Impact: ~500ms extra

3. **query_parser + query_analyzer:**
   - 2 LLM Calls pro Query (könnte zu 1 zusammengefasst werden)
   - Performance-Impact: ~2-3s extra

---

## 📞 Bei Problemen

**Logs sammeln:**
```bash
# Backend Logs (letzte 100 Zeilen)
tail -n 100 logs/backend.log

# Nur Errors
grep ERROR logs/backend.log

# Temporal Parsing
grep "Using LLM-parsed temporal filter" logs/backend.log
```

**Screenshots:**
- Network Tab (zeigt SSE Chunks)
- Timeline (zeigt wann Events erscheinen)
- Query-Analyse (aufgeklappt)
- Console Errors (falls vorhanden)

**Kontakt:**
- @prompt-engineer für Prompt-Probleme
- @architect für Architektur-Fragen
- Claude Code für Bug-Fixes

---

**Status:** 🟡 Ready for @qs Testing
**Next Steps:** @qs führt Tests durch → Bug Report → Fixes → Re-Test → @bd Approval
