# Thinking Timeline – Transparente Agenten-Gedanken

## 🎯 Übersicht

Das **Thinking Timeline Feature** macht den kompletten Reasoning-Prozess des AI-Agenten in Echtzeit sichtbar. Jeder gedankliche Zwischenschritt wird sofort im Frontend als interaktive Timeline angezeigt.

## 🔄 Architektur

### Backend → Frontend Event-Flow

```
User Query
    ↓
[Query Analyzer]
    ↓ Event: query_analysis
[Frontend: Zeige Analyse-Schritt]
    ↓
[ReAct Agent: Thought]
    ↓ Event: thought
[Frontend: Zeige Gedanken-Schritt]
    ↓
[ReAct Agent: Tool Call]
    ↓ Event: tool_call
[Frontend: Zeige Tool-Aufruf (⚙️ running)]
    ↓
[Tool Execution: search_photos]
    ↓ Event: tool_result
[Frontend: Update Tool-Status (✓ success)]
    ↓
[ReAct Agent: Final Thought]
    ↓ Event: thought ("Formuliere Antwort...")
[Frontend: Zeige finalen Schritt]
    ↓
[LLM: Generate Answer]
    ↓ Event: text
[Frontend: Zeige Antwort-Bubble]
```

## 📊 Event-Types

### 1. `query_analysis`
Zeigt die initiale Analyse der Nutzeranfrage.

**Payload:**
```json
{
  "type": "query_analysis",
  "content": {
    "query_type": "multi_entity_reasoning",
    "complexity": "medium",
    "sub_queries": [
      "Schritt 1: Finde Zeitraum des München-Trips",
      "Schritt 2: Suche Sarah-Nachrichten in diesem Zeitraum"
    ],
    "temporal_fuzzy": false,
    "entities": ["Sarah", "München"],
    "reasoning": "Multi-Hop: Datum unbekannt → erst Fotos, dann Messages"
  }
}
```

**Frontend-Darstellung:**
```
┌───────────────────────────────────────┐
│ 🧠 Query-Analyse                 ✓   │
│ ├─ Typ: Multi-Entitäten-Analyse      │
│ ├─ Komplexität: medium               │
│ ├─ Entitäten: Sarah, München         │
│ └─ Geplante Schritte: 2              │
└───────────────────────────────────────┘
```

### 2. `thought`
Zeigt einen Reasoning-Schritt des Agenten (ReAct Pattern).

**Payload:**
```json
{
  "type": "thought",
  "content": "Ich suche zuerst nach Fotos in München, um das Datum zu finden."
}
```

**Frontend-Darstellung:**
```
┌───────────────────────────────────────┐
│ 💭 Ich suche zuerst nach Fotos in    │
│    München, um das Datum zu finden.  │
└───────────────────────────────────────┘
```

### 3. `tool_call`
Zeigt den Aufruf eines Tools (Action im ReAct-Pattern).

**Payload:**
```json
{
  "type": "tool_call",
  "content": {
    "tool": "search_photos",
    "args": {
      "orte": ["München"],
      "von_datum": "2024-08-01",
      "bis_datum": "2024-08-31"
    },
    "status": "running"
  }
}
```

**Frontend-Darstellung:**
```
┌───────────────────────────────────────┐
│ 📷 Tool: search_photos           ⚙️  │
│ orte=["München"], von_datum="2024-..." │
└───────────────────────────────────────┘
```

### 4. `tool_result`
Aktualisiert den Status eines Tool-Aufrufs (Observation).

**Payload:**
```json
{
  "type": "tool_result",
  "content": {
    "tool": "search_photos",
    "summary": "12 neue Quellen",
    "status": "success"
  }
}
```

**Frontend-Darstellung:**
```
┌───────────────────────────────────────┐
│ 📷 Tool: search_photos            ✓  │
│ orte=["München"], von_datum="2024-..." │
│ → 12 neue Quellen                     │
└───────────────────────────────────────┘
```

## 🎨 UI-Features

### Progressive Disclosure
- Timeline standardmäßig **aufgeklappt** während Agent arbeitet
- Nach Fertigstellung: Automatisch einklappbar via Toggle-Button
- Smooth Expand/Collapse-Animationen

### Visual Coding
| Farbe | Bedeutung |
|-------|-----------|
| 🔵 Blau | Query-Analyse |
| 💠 Cyan | Thought (Reasoning) |
| 🟡 Gelb | Tool Call (Running) |
| 🟢 Grün | Success |
| 🔴 Rot | Error |

### Animationen
- **FadeIn**: Neue Schritte erscheinen smooth von oben
- **Pulse**: Aktive Tool-Calls pulsieren
- **Hover**: Steps heben sich bei Mouseover leicht an

## 🔧 Technische Details

### Backend (Python)

**connector.py** (`chat_stream`):
- Detektiert Tool-Calls in Gemini-Responses
- Generiert granulare Events (thought → tool_call → tool_result)
- Parst Tool-Returns für strukturierte Observations

**retriever_v2.py** (`answer_v2_stream`):
- Integriert Query-Analyzer vor der eigentlichen Suche
- Sendet `query_analysis` Event mit Metadaten

### Frontend (JavaScript)

**chat.js**:
- `createStreamingAssistantMessageCard()`: Erstellt Timeline-Container
- `addQueryAnalysisStep()`: Rendert Analyse-Schritt
- `addThoughtStep()`: Rendert Gedanken-Schritt
- `addToolCallStep()`: Rendert Tool-Aufruf (gibt stepId zurück)
- `updateToolResultStep()`: Aktualisiert Tool-Status via stepId

**index.html**:
- CSS Keyframe-Animationen für smooth Transitions
- Gradient-Backgrounds für visuellen Appeal

## 📈 Performance-Überlegungen

### Token-Overhead
- **Pro Query**: ~50-100 zusätzliche Tokens für Events
- **Mitigation**: Nur bei komplexen Queries (complexity > simple)

### Latency
- **Event-Serialisierung**: ~2-5ms pro Event
- **Frontend-Rendering**: ~10-20ms pro Step
- **Gesamt**: Vernachlässigbar (<100ms für 5 Steps)

### State-Management
- Timeline-State wird in `responseUi` Objekt gehalten
- `stepCounter` für eindeutige IDs bei Tool-Calls
- `lastToolStepId` für Update-Referenz

## 🚀 Aktivierung

### Automatisch
Das Feature ist standardmäßig für **alle Gemini-Provider** aktiviert.

### Fallback
- Nicht-Gemini-Provider zeigen weiterhin alte "plan"-Events
- Legacy-Support bleibt vollständig erhalten

### Optional Disablen
Nutzer können Timeline via Settings ausblenden:
```javascript
localStorage.setItem('DISABLE_THINKING_TIMELINE', 'true');
```

## 🔍 Debugging

### Frontend-Logs
```javascript
localStorage.setItem('DEBUG', 'true');
// Zeigt alle SSE-Events in Browser-Console
```

### Backend-Logs
```python
# In retriever_v2.py / connector.py
logger.setLevel(logging.DEBUG)
# Zeigt alle Tool-Calls und Events
```

## 🎯 Beispiel-Output

```markdown
User: "Was habe ich mit Nora in München gemacht?"

[Timeline]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 QUERY-ANALYSE                       ✓
   Typ: Multi-Entitäten-Analyse
   Komplexität: medium
   Entitäten: Nora, München
   Geplante Schritte: 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💭 Ich suche zuerst nach Fotos in München...

📷 Tool: search_photos                 ⚙️
   orte=["München"]
   → 12 neue Quellen                   ✓

💭 Jetzt filtere ich nach Nora...

📷 Tool: search_photos                 ⚙️
   personen=["Nora"], orte=["München"]
   → 8 neue Quellen                    ✓

💭 Formuliere finale Antwort...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Antwort-Bubble]
Du warst im August 2024 mit Nora in **München-Schwabing** [[1]].
Auf den Fotos sieht man euch am Englischen Garten [[2]] und
am Marienplatz [[3]].
```

## 🔗 Verwandte Dokumentation

- [PROMPT_BEST_PRACTICES.md](./PROMPT_BEST_PRACTICES.md) - ReAct Pattern Guidelines
- [backend/rag/query_analyzer.py](../backend/rag/query_analyzer.py) - Query Decomposition Logic
- [backend/llm/connector.py](../backend/llm/connector.py) - LLM Streaming Implementation
