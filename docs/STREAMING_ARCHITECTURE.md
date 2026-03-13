# Real-Time Denkprozess Streaming - Architektur

**Datum:** 2026-03-10
**Status:** 🟢 Implementierung Ready
**Teams:** @architect, @ux, @prompt-engineer, @bd

---

## 🎯 Problem Statement (@bd)

**Aktuell:** User sieht erst Ergebnis, dann zu detaillierten "Denkprozess"
**Gewünscht:** User sieht **während** der Arbeit live was passiert (wie GitHub Copilot, Cursor, Claude Code)

**User Value:**
- ✅ Transparenz: "Was macht die KI gerade?"
- ✅ Vertrauen: "Sehe, dass nach richtigen Quellen gesucht wird"
- ✅ Debugging: "Warum findet sie nichts? Ah, falscher Datumsfilter!"
- ✅ Perceived Performance: Wartezeit fühlt sich kürzer an

---

## 🏗️ System-Architektur (@architect)

### Komponenten

```
┌─────────────────────────────────────────────────────────────┐
│                      USER QUERY                              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: answer_v3_stream()                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Query Analysis → yield {type:"query_analysis"}    │   │
│  │ 2. Synonym Expansion → yield {type:"thought"}        │   │
│  │ 3. Multi-Shot Retrieval → yield {type:"retrieval"}   │   │
│  │ 4. Progressive Context → yield {type:"thought"}      │   │
│  │ 5. LLM Streaming → yield {type:"text"}              │   │
│  │ 6. Sources → yield {type:"sources"}                  │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────┬────────────────────────────────────────────┘
                 │ SSE (Server-Sent Events)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend: chat.js (Event Listener)                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ • query_analysis → Show "📊 Analysiere Anfrage..."   │   │
│  │ • thought → Show "💭 Erweitere Suche..."            │   │
│  │ • retrieval → Show "🔍 Suche in Fotos (3/5)..."     │   │
│  │ • text → Append to answer (char by char)            │   │
│  │ • sources → Show source cards                        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Event Schema (JSON)

```typescript
// 1. Query Analysis
{
  "type": "query_analysis",
  "content": {
    "query": "Wo war ich gestern mit Anna?",
    "persons": ["Anna"],
    "date_from": "2026-03-09",
    "date_to": "2026-03-09",
    "collections": ["photos", "messages"],
    "complexity": "medium"
  }
}

// 2. Thought (Internal Reasoning)
{
  "type": "thought",
  "content": "Erweitere Suche mit Synonymen: 'Wo' → 'Ort', 'Platz', 'Location'"
}

// 3. Retrieval Progress
{
  "type": "retrieval",
  "content": {
    "collection": "photos",
    "query_variant": "Ort mit Anna gestern",
    "results_count": 3,
    "temporal_range": "2026-03-09",
    "progress": "3/5"  // 3 von 5 Collections durchsucht
  }
}

// 4. Text (Streaming Answer)
{
  "type": "text",
  "content": "Gestern warst du "  // Chunk by chunk
}

// 5. Sources (Final Results)
{
  "type": "sources",
  "content": [
    {"id": "...", "collection": "photos", "score": 0.89, ...}
  ]
}

// 6. Error
{
  "type": "error",
  "content": "Elasticsearch nicht erreichbar, nutze ChromaDB Fallback"
}
```

---

## 🎨 UX Design (@ux)

### User Flow (Streaming Timeline)

```
┌────────────────────────────────────────────────────────────┐
│ 🦕 2nd Memory                                         [Stop] │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Du: Wo war ich gestern mit Anna?                         │
│                                                             │
│  🦕 2nd Memory:                                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 📊 Analysiere Anfrage...                    ✓ 0.2s  │  │
│  │    • Personen: Anna                                  │  │
│  │    • Zeitraum: 09.03.2026 (gestern)                 │  │
│  │    • Collections: Fotos, Nachrichten                │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ 🔍 Suche in Fotos (1/2)...              ⏳ läuft   │  │
│  │    • Query: "Ort mit Anna gestern"                   │  │
│  │    • Gefunden: 3 Ergebnisse                         │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ 🔍 Suche in Nachrichten (2/2)...        ⏳ läuft   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  Gestern warst du mit Anna im Restaurant Poseidon...      │
│  [Text wird live gestreamt]                                │
│                                                             │
│  📸 Quellen (5)                                            │
│  [Photos & Messages Cards]                                 │
└────────────────────────────────────────────────────────────┘
```

### UI States

1. **Query Analysis Phase** (0.1-0.5s)
   - Icon: 📊 (blau, pulsierend)
   - Text: "Analysiere Anfrage..."
   - Details: Collapsible (zeigt Personen, Datum, Collections)
   - Status: ✓ nach Completion

2. **Retrieval Phase** (0.5-2s)
   - Icon: 🔍 (orange, animated search)
   - Text: "Suche in Fotos (1/2)..."
   - Progress Bar: 50% → 100%
   - Details: Query-Variante + Ergebnis-Count
   - Status: ✓ nach Completion

3. **Thought Phase** (0.1-0.3s)
   - Icon: 💭 (grau, optional ausblendbar)
   - Text: "Erweitere Suche mit Synonymen..."
   - Details: Nur bei Debug-Mode sichtbar
   - Status: Auto-hide nach 2s (oder Collapsible)

4. **Answer Streaming** (1-5s)
   - Live-Text wie bisher
   - Cursor blinkt während Streaming
   - Markdown-Rendering in real-time

5. **Sources** (Final)
   - Cards wie bisher
   - Inline-Referenzen [[1]], [[2]] klickbar

---

## 🎙️ Prompt Engineering (@prompt-engineer)

### System Prompt für Streaming

```python
system_prompt = f"""AKTUELLES DATUM: {current_date}

Du bist 2nd Memory, ein analytischer RAG-Agent.

## WICHTIG: Real-Time Streaming Mode

Du arbeitest im **Streaming-Modus**. Das bedeutet:

1. **Vor jedem Tool-Call**: Erkläre KURZ (1 Satz) was du tust
   Beispiel: "Ich suche jetzt in Fotos nach Anna vom 09.03.2026."

2. **Nach jedem Retrieval**: Fasse kurz zusammen (1 Satz)
   Beispiel: "Ich habe 3 Fotos gefunden."

3. **Finale Antwort**: Streame normal wie gewohnt

## Regeln
- Halte "Thoughts" SEHR kurz (max 10 Wörter)
- Nutze Tools nur wenn nötig (User sieht jeden Call)
- Zeige NUR relevante Zwischenschritte (kein Debug-Spam)
"""
```

### Thought-Strategie (Chain-of-Thought)

**Aktuell (v3):**
```python
# ❌ Zu detailliert, nicht gestreamt
reasoning_steps = [
    "Schritt 1: Suche Personen → 3 Quellen",
    "Schritt 2: Suche Orte → 5 Quellen",
    "Schritt 3: Kombiniere Ergebnisse"
]
# Wird NACH Antwort gezeigt
```

**Neu (Streaming):**
```python
# ✅ Live während der Arbeit
async def answer_v3_stream():
    # 1. Query Analysis
    yield {"type": "query_analysis", "content": {...}}

    # 2. Retrieval mit Progress
    for i, collection in enumerate(collections):
        yield {"type": "retrieval", "content": {
            "collection": collection,
            "progress": f"{i+1}/{len(collections)}"
        }}
        results = await retrieve(collection, ...)

    # 3. Streaming Answer
    async for chunk in llm_stream(...):
        yield {"type": "text", "content": chunk}
```

---

## 📋 Implementation Plan (@architect)

### Phase 1: Backend Streaming (2-3h)

**Dateien:**
- `backend/rag/retriever_v3.py`: Neue Funktion `answer_v3_stream()`
- `backend/api/v1/query.py`: Endpoint `/query_stream` nutzt `answer_v3_stream()`

**Tasks:**
1. ✅ `async def answer_v3_stream()` erstellen
2. ✅ Yield Events während Query-Analyse
3. ✅ Yield Events während Multi-Shot Retrieval
4. ✅ Yield Events während LLM Streaming
5. ✅ Error Handling (yield `error` Events)

### Phase 2: Frontend Updates (1-2h)

**Dateien:**
- `frontend/chat.js`: Event-Handler erweitern

**Tasks:**
1. ✅ `addQueryAnalysisStep()` implementieren
2. ✅ `addRetrievalStep()` mit Progress Bar
3. ✅ `addThoughtStep()` mit Auto-Collapse
4. ✅ Collapsible Details (Click to Expand)

### Phase 3: Prompt Optimization (1h)

**Dateien:**
- `backend/rag/retriever_v3.py`: `_get_system_prompt_v3()` anpassen

**Tasks:**
1. ✅ Kurze "Thought"-Instructions hinzufügen
2. ✅ Examples für gute vs. schlechte Thoughts
3. ✅ A/B Test: Streaming mit/ohne Thoughts

---

## ⚠️ Anti-Patterns (von @qs)

**DON'Ts:**
- ❌ Zu viele Events (>10 pro Query) → Spam
- ❌ Zu lange Thoughts (>20 Wörter) → Noise
- ❌ Debug-Logs als Thoughts → Nutzer-Verwirrung
- ❌ Events ohne Kontext ("Schritt 3") → Was ist Schritt 3?
- ❌ Blocking Events (warten auf User) → Nur Info, kein Input

**DOs:**
- ✅ Max 5-7 Steps pro Query
- ✅ Kurze, nutzer-freundliche Beschreibungen
- ✅ Progress-Indikatoren (1/3, 2/3, 3/3)
- ✅ Auto-Collapse Details nach 3s
- ✅ [Stop]-Button prominent (User-Control)

---

## 🧪 Testing Strategy (@qs)

### Test Cases

1. **Simple Query** (keine Thoughts nötig)
   - "Zeige mir Fotos von gestern"
   - Erwartung: Nur `query_analysis` + `retrieval` + `text`

2. **Complex Query** (mit Chain-of-Thought)
   - "Wo war ich letztes Jahr im August mit Anna?"
   - Erwartung: `query_analysis` + 3x `retrieval` + `thought` + `text`

3. **No Results** (Fallback)
   - "Was habe ich heute gemacht?" (keine Daten)
   - Erwartung: `query_analysis` + `retrieval` (empty) + `text` (Hilfe-Nachricht)

4. **Error Handling**
   - Elasticsearch down → ChromaDB Fallback
   - Erwartung: `error` Event + `retrieval` (ChromaDB) + `text`

### Success Metrics (@bd)

- **User Satisfaction**: Daumen hoch/runter nach Antwort
- **Perceived Speed**: Fühlt sich <2s an (auch wenn 5s real)
- **Abort Rate**: <5% klicken [Stop] während Streaming
- **Engagement**: >80% klappen Details auf (Curiosity)

---

## 📞 Coordination (@architect)

**Rollen-Verteilung:**
- **@architect**: Koordination + Backend-Struktur
- **@prompt-engineer**: System-Prompts + Thought-Strategien
- **@ux**: UI-Components + Wireframes
- **@coder**: Implementation (Backend + Frontend)
- **@qs**: Testing + Verification

**Meilensteine:**
1. ✅ Konzept fertig (JETZT)
2. [ ] Backend Streaming implementiert (3h)
3. [ ] Frontend Updates implementiert (2h)
4. [ ] Tests grün (1h)
5. [ ] User Testing (Optional, 1 Tag)

---

## 🚀 Next Steps

**JETZT:**
- [ ] @architect: Review dieses Dokument mit User
- [ ] User Approval einholen

**DANACH:**
- [ ] @coder: Implementiere `answer_v3_stream()` (Backend)
- [ ] @coder: Implementiere Event-Handler (Frontend)
- [ ] @prompt-engineer: Optimiere System-Prompt
- [ ] @qs: Schreibe Tests + Verify

**SPÄTER:**
- [ ] A/B Test: Mit/Ohne Thoughts
- [ ] Analytics: Track welche Events User aufklappen
- [ ] Optimierung: Reduce Events bei Simple Queries

---

**Dokument-Status:** ✅ Ready for Review
**Nächster Reviewer:** User (für Approval)
