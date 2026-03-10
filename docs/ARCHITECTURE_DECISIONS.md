# Architektur-Entscheidungen: RAG v3 Upgrade
**Datum:** 2026-03-10
**Entscheidungsträger:** User + @architect + @prompt-engineer

---

## Kontext
User hat 4 kritische Query-Typen identifiziert, die RAG v2 nicht gut beantwortet:
1. Temporale Unschärfe ("letzten Sommer")
2. User-Fehlertoleranz ("letztes Jahr" meint 2024, nicht 2025)
3. Multi-Hop Reasoning ("Was kann ich Sarah schenken?")
4. Semantische Expansion ("Tiefbauunternehmen" = "Baufirma")

**Ziel**: RAG v3 mit Chain-of-Thought, Query Decomposition, Temporal Fuzzy Logic

---

## Entscheidungen

### 1. Modul-Struktur ✅
**Entscheidung**: **Separate Module**

```
backend/rag/
├── query_parser.py          ← Bestehendes Modul (regelbasiert, bleibt)
├── query_analyzer.py        ← NEU (LLM-basiert, komplexe Queries)
├── temporal_utils.py        ← NEU (Fuzzy Temporal Expansion)
├── retriever_v2.py          ← Bestehend (wird erweitert)
├── retriever_v3.py          ← NEU (parallel zu v2)
└── context_manager.py       ← NEU (bereits implementiert ✅)
```

**Begründung**:
- Clean Separation of Concerns
- query_parser.py bleibt für einfache regelbasierte Queries
- query_analyzer.py für komplexe LLM-basierte Dekomposition
- Einfacher zu testen und zu warten

---

### 2. Retriever v3 - Parallel Betrieb ✅
**Entscheidung**: **v2 und v3 laufen parallel**

```python
# Config-basiert
if config["rag"]["use_v3"]:
    from backend.rag.retriever_v3 import retrieve, answer_stream
else:
    from backend.rag.retriever_v2 import retrieve_v2 as retrieve, answer_v2_stream as answer_stream
```

**Begründung**:
- Sicherer Rollout (v2 als Fallback)
- Einfaches Rollback bei Problemen
- Gradual Migration möglich

**Kein A/B Testing nötig** (User-Entscheidung):
- Grund: Noch keine große User-Masse
- Einfaches Feature-Flag statt komplexes A/B Framework

---

### 3. API-Endpoints ✅
**Entscheidung**: **Erweitere bestehende /api/v1/ Endpoints**

**KEIN** neues `/api/v3/` nötig.

**Bestehend**:
```
GET /api/v1/query/answer?q=...
→ SSE Stream
```

**Erweitert** (Chain-of-Thought):
```
GET /api/v1/query/answer?q=...&mode=chain_of_thought
→ SSE Stream mit neuen Event-Types:
  {"type": "step", "content": "Schritt 1: ..."}
  {"type": "sources", "content": [...]}
  {"type": "text", "content": "..."}
```

**Begründung**:
- Backward compatible (alte Clients funktionieren weiter)
- Query-Parameter `mode=chain_of_thought` opt-in
- Kein Breaking Change

---

### 4. Testing-Strategie ✅
**Entscheidung**: **Wie vorgeschlagen**

```
tests/
├── backend/
│   ├── rag/
│   │   ├── test_context_manager.py      ← ✅ Bereits vorhanden
│   │   ├── test_query_analyzer.py       ← NEU (Phase 1)
│   │   ├── test_temporal_utils.py       ← NEU (Phase 1)
│   │   └── test_retriever_integration.py ← NEU (Phase 2, E2E)
```

**Keine separaten A/B Tests** (User-Entscheidung)

---

### 5. Deployment Dependencies ✅
**Entscheidung**: **Leg los mit tiktoken**

```bash
pip install tiktoken>=0.8.0
```

**Keine Build-Tests nötig** (User-Freigabe)
- Tiktoken funktioniert auf allen gängigen Plattformen (x86, ARM)
- In requirements.txt bereits hinzugefügt ✅

---

## Team-Struktur

### @prompt-engineer (Lead für RAG v3)
**Aufgaben**:
- ✅ Context Management (abgeschlossen)
- 🔄 Phase 1: query_analyzer.py, temporal_utils.py
- 🔜 Phase 2: retriever_v3.py
- 🔜 Phase 3: Chain-of-Thought Integration
- System Prompts designen & optimieren

**Kann Support holen von**:
- @architect: API-Design, System-Architektur
- @chat-rag-dev: RAG Pipeline Integration
- @tester: Test-Suite Erstellung

### @architect
**Aufgaben**:
- Review Code-Struktur (Phase 1 → Phase 3)
- API-Endpoint Design (Chain-of-Thought SSE Format)
- Config-Management (Feature-Flags für v2/v3)
- Deployment-Koordination

### @chat-rag-dev (Support)
**Aufgaben** (nach Phase 1):
- Integration retriever_v3 in bestehende API
- SSE Event-Handling für Chain-of-Thought
- Error-Handling & Fallback-Logic

### @tester (Support)
**Aufgaben** (nach Phase 2):
- Integration Tests schreiben
- End-to-End Tests mit echten Queries
- Performance Tests (Token-Usage, Latenz)

---

## Rollout-Plan

### Phase 1: Foundation (1-2 Tage) 🔄 IN PROGRESS
**Owner**: @prompt-engineer
- [ ] query_analyzer.py (LLM-basierte Query Decomposition)
- [ ] temporal_utils.py (Fuzzy Temporal Expansion)
- [ ] Tests schreiben
- [ ] tiktoken installieren

**Deliverable**: Funktionale Module, getestet

---

### Phase 2: Retriever v3 (2-3 Tage)
**Owner**: @prompt-engineer + @chat-rag-dev
- [ ] retriever_v3.py mit Multi-Shot Retrieval
- [ ] Synonym-Expansion via LLM
- [ ] Fallback-Strategien
- [ ] Integration in API (Config-basiert)
- [ ] Integration Tests

**Deliverable**: retriever_v3 parallel zu v2 lauffähig

---

### Phase 3: Chain-of-Thought (2 Tage)
**Owner**: @prompt-engineer + @chat-rag-dev
- [ ] answer_v3_stream() mit Sub-Query Execution
- [ ] SSE Event-Types erweitern (step, sources)
- [ ] Frontend: Chain-of-Thought Visualisierung
- [ ] E2E Tests

**Deliverable**: Chain-of-Thought produktionsbereit

---

### Phase 4: Rollout (1 Tag)
**Owner**: @architect + @prompt-engineer
- [ ] Config-Flag setzen (use_v3: false → true)
- [ ] Monitoring aktivieren (Token-Usage, Latenz)
- [ ] Dokumentation für User
- [ ] Rollback-Plan testen

**Deliverable**: v3 in Production

---

## Feature-Flag Config

**Neu in config.yaml**:
```yaml
rag:
  version: "v2"  # "v2" | "v3"

  # v3-spezifische Settings
  v3:
    enable_query_decomposition: true
    enable_temporal_fuzzy: true
    enable_synonym_expansion: true
    max_sub_queries: 5

  # Context Management (bereits aktiv)
  context:
    compression_threshold: 15  # Aktiviere Kompression ab 15 Quellen
    max_tokens: 8000
    top_n_full: 5
```

---

## Erfolgs-Metriken

**Keine A/B Tests**, aber manuelles Tracking:

### Qualität
- [ ] "Wo war ich letzten Sommer?" → Korrekte Antwort
- [ ] "Wie hieß die Kneipe in Brandenburg?" → Findet trotz Jahr-Fehler
- [ ] "Was kann ich Sarah schenken?" → Inferiert Interessen
- [ ] "Wann will das Tiefbauunternehmen...?" → Findet in Messages

### Performance
- [ ] Token-Usage: <8k tokens pro Query (auch bei Chain-of-Thought)
- [ ] Latenz: <5s für komplexe Queries
- [ ] Recall: >85% (vs. 40% in v2)

### User-Feedback
- [ ] User-Zufriedenheit: >4/5 (aktuell 3.2/5)

---

## Risiken & Mitigation

### Risiko 1: v3 ist langsamer als v2
**Wahrscheinlichkeit**: Mittel
**Impact**: Hoch
**Mitigation**:
- Zeige Chain-of-Thought Steps im Frontend (transparente Wartezeit)
- Config-Flag erlaubt schnelles Rollback zu v2

### Risiko 2: LLM-Kosten steigen (Query Decomposition)
**Wahrscheinlichkeit**: Hoch
**Impact**: Mittel
**Mitigation**:
- Cache häufige Query-Patterns
- Regelbasierter Fallback für einfache Queries (query_parser.py)

### Risiko 3: Temporal Fuzzy Logic gibt falsche Daten
**Wahrscheinlichkeit**: Niedrig
**Impact**: Hoch
**Mitigation**:
- Zeige erkannte Zeiträume im UI (User kann korrigieren)
- Logging aller temporalen Expansionen für Debugging

---

## Offene Fragen

- [ ] @chat-rag-dev: Kannst du SSE Event-Handling für "step" Events übernehmen? (Phase 3)
- [ ] @architect: Brauchen wir zusätzliche Monitoring-Metriken?
- [ ] @tester: Welche Edge-Cases sollen wir testen?

---

## Zusammenfassung

✅ **Entscheidungen getroffen**:
1. Separate Module (query_analyzer.py, temporal_utils.py)
2. v2 und v3 parallel (Config-Flag)
3. API v1 erweitern (kein v3 Endpoint)
4. Testing wie vorgeschlagen
5. tiktoken sofort installieren

🚀 **Nächster Schritt**: @prompt-engineer startet Phase 1 (query_analyzer.py + temporal_utils.py)

🤝 **Collaboration**: @prompt-engineer kann Support von @architect, @chat-rag-dev, @tester holen

📅 **Timeline**: ~1 Woche bis v3 Production-ready
