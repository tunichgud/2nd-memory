# Multi-Agent Setup für Antigravity
## Node.js + Python Full-Stack · Claude Sonnet

---

## Übersicht

Dieses Setup definiert **10 spezialisierte Agenten** für den **Antigravity Manager View**.
Jeder Agent hat eine klare Rolle und Übergabepunkte an den nächsten.

```
Business Goal / Feature Idea
      │
      ▼
┌───────────────────────────────────────────┐
│         PRODUCT & UX (parallel)           │
├─────────────────┬─────────────────────────┤
│       BD        │         UX              │
│  (Thinking)     │     (Standard)          │
│  Requirements   │   User Flows            │
│  Prioritization │   Wireframes            │
└────────┬────────┴─────────┬───────────────┘
         │                  │
         └──────────┬───────┘
                    ▼
         ┌─────────────────┐
         │   ARCHITECT     │  Plant · Spezifiziert · Fragt nach
         │   (Thinking)    │
         └────────┬────────┘
                  │ Approved Plan
                  ▼
┌────────────────────────────────────────────────────────┐
│           FEATURE DEVELOPERS (parallel)                │
├────────────────┬────────────────┬────────────┬─────────┤
│ WhatsApp-Dev   │  FaceRec-Dev   │ ChatRAG-Dev│ General │
│   (Standard)   │   (Standard)   │  (Standard)│ (Std.)  │
└────────┬───────┴────────┬───────┴──────┬─────┴────┬────┘
         │                │              │          │
         └────────────────┴──────────────┴──────────┘
                          │
                          ▼
                    ┌──────────┐
                    │  TESTER  │  Testet · Blockiert bei Fehlern
                    │(Standard)│
                    └─────┬────┘
                          │ Tests grün
                          ▼
         ┌────────────────┴────────────────┐
         │                                  │
    ┌────┴──────┐                   ┌──────┴────┐
    │    QS     │                   │  SCRIBE   │
    │(Thinking) │                   │ (Standard)│
    │Quality    │                   └───────────┘
    │Assurance  │
    └───────────┘
```

### Agent-Domains

**Strategy:** Product Manager (BD) + UX Manager (2, parallel möglich)
  - `@bd`: Requirements, Prioritization, Success Metrics, Go-to-Market
  - `@ux`: User Flows, Wireframes, Accessibility, Interaction Design

**Planning:** Architect (1)

**Implementation:** 4 Feature-Developers (parallel execution möglich)
  - `@whatsapp-dev`: WhatsApp, Import, Bot
  - `@face-recognition-dev`: Face Detection, Clustering, Entities
  - `@chat-rag-dev`: Chat UI, RAG Pipeline, LLM
  - `@general-dev`: Infrastructure, Config, Media, Maps

**Quality:** Tester (1) + QS (Quality Assurance) (1)

**Maintenance:** Scribe (1)

---

## Installation

1. Diesen `.antigravity/` Ordner in dein **Projekt-Root** kopieren
2. Antigravity öffnen → Manager View
3. Agenten über die Prompt-Eingabe aufrufen (siehe unten)

---

## Agenten aufrufen

### Im Manager View — neue Mission starten:

**Product Manager** (bei neuen Business-Anforderungen, OPTIONAL aber empfohlen):
```
@bd Wir wollen [Business Goal]. Erstelle ein PRD mit User Stories und Priorisierung.
```

**UX Manager** (bei UI/UX-Änderungen, parallel zu BD möglich):
```
@ux Designe den User Flow für [Feature] mit Wireframes und Interaktionsstaten.
```

**Architect** (immer bei neuen Features):
```
@architect Ich möchte [Feature] implementieren. Erstelle einen Plan.
```

**Feature Developers** (nach Architect-Freigabe, wähle passenden Spezialisten):

```
@whatsapp-dev Implementiere WhatsApp [Import/Bot/Message] Feature gemäß Plan.
@face-recognition-dev Implementiere Face [Detection/Clustering/Assignment] gemäß Plan.
@chat-rag-dev Implementiere Chat/RAG [Search/LLM/UI] Feature gemäß Plan.
@general-dev Implementiere [Config/Media/Infrastructure] gemäß Plan.
```

**Tester** (nach Developer):
```
@tester Schreibe und führe Tests für die Änderungen in [Files] aus.
```

**QS (Quality Assurance)** (User meldet Bug, nach Tester, oder on-demand):
```
@qs [User beschreibt Bug] → QS übernimmt Koordination und Tracking
@qs Überprüfe die Logs auf Fehler und koordiniere Bug-Fixes.
@qs Verifiziere dass [Bug/Feature] vollständig getestet und fehlerfrei ist.
```

**Wichtig**: Wenn der User einen Bug meldet, immer `@qs` nutzen - QS koordiniert dann den Fix!

**Scribe** (nach Feature-Completion):
```
@scribe Dokumentiere die Änderungen aus [Developer-Artifact] auf Deutsch und Englisch.
```

### Welchen Developer wählen?

**Frage dich:**
- Betrifft es WhatsApp? → `@whatsapp-dev`
- Betrifft es Gesichter/Fotos/Personen? → `@face-recognition-dev`
- Betrifft es Chat/Suche/LLM? → `@chat-rag-dev`
- Alles andere? → `@general-dev`

**Beispiele:**
- "Import WhatsApp History" → `@whatsapp-dev`
- "Assign faces to entities" → `@face-recognition-dev`
- "Improve search relevance" → `@chat-rag-dev`
- "Add photo thumbnails" → `@general-dev`

---

## Parallel-Workflows im Manager View

Antigravity erlaubt mehrere Agenten gleichzeitig. Sinnvolle Kombinationen:

| Parallel | Warum |
|----------|-------|
| **BD + UX** | Requirements und User Flows gleichzeitig entwickeln |
| **BD + Architect** | PRD schreiben während Technical Design entsteht |
| **UX + Frontend Developer** | Wireframes → Implementation ohne Wartezeit |
| Tester + Scribe | Tests schreiben während Docs entstehen |
| Tester + QS | Tests schreiben während Logs analysiert werden |
| Architect (Feature A) + Developer (Feature B) | Planung läuft vor, Implementation folgt |
| WhatsApp-Dev + Face-Recognition-Dev | Unabhängige Domains, keine File-Konflikte |
| Chat-RAG-Dev + General-Dev | Backend vs. Frontend/Infrastructure |
| QS + Scribe | Logs prüfen + dokumentieren gleichzeitig |

**Nicht parallel:**
- BD + Developer (ohne Architect dazwischen — PRD muss erst in Technical Plan übersetzt werden)
- Architect + Developer am gleichen Feature (Developer wartet auf Plan)
- Zwei Developers auf derselben Datei (Race condition)
- WhatsApp-Dev + General-Dev auf `backend/main.py` (Router registration conflict)

---

## Modell-Konfiguration

| Agent | Modus | Warum |
|-------|-------|-------|
| **BD (Product Manager)** | **Sonnet Thinking** | Strategische Priorisierung, Business-Impact-Analyse |
| **UX Manager** | **Sonnet Standard** | UI-Patterns sind etabliert, kein Deep Thinking |
| Architect | Sonnet Thinking | Braucht tiefes Reasoning für Planung |
| WhatsApp-Dev | Sonnet Standard | Feature-fokussiert, klare Patterns |
| Face-Recognition-Dev | Sonnet Standard | CV-Algorithmen, numerische Arbeit |
| Chat-RAG-Dev | Sonnet Standard | RAG-Pipeline, bekannte Patterns |
| General-Dev | Sonnet Standard | Infrastructure, repetitive Tasks |
| Tester | Sonnet Standard | Regelbasiert, kein Deep Thinking nötig |
| **QS (Quality Assurance)** | **Sonnet Thinking** | Log-Analyse, Root-Cause-Diagnose, Bug-Koordination |
| Scribe | Sonnet Standard | Dokumentation ist repetitiv |

---

## Dateien in diesem Setup

```
.antigravity/
├── README.md                    ← Diese Datei
├── rules.md                     ← Globale Regeln (alle Agenten lesen das)
├── bd.md                        ← Product Manager (Business/Strategy)
├── ux.md                        ← UX Manager (User Flows/Wireframes)
├── architect.md                 ← Planungs-Agent (Technical Design)
├── whatsapp-dev.md             ← WhatsApp Feature Developer
├── face-recognition-dev.md     ← Face Recognition Developer
├── chat-rag-dev.md             ← Chat & RAG Developer
├── general-dev.md              ← General Infrastructure Developer
├── tester.md                   ← Test-Agent
├── qs.md                       ← Quality Assurance Agent (Log-Analyse, Bug-Koordination)
├── scribe.md                   ← Dokumentations-Agent
├── prompt-engineer.md          ← Prompt Engineering Specialist
└── coder.md                    ← Legacy (ersetzt durch 4 Feature-Devs)
```

---

## Tipps

- **Bug gefunden? Immer zu QS!** — `@qs [Bug-Beschreibung]` koordiniert die komplette Behebung
- **Strategische Features? Start mit BD** — Business Value klären, bevor du baust
- **UI-Changes? Start mit UX** — Wireframes verhindern 3 Redesign-Runden
- **Starte immer mit Architect** — auch für kleine Features. 2 Minuten Planung spart 20 Minuten Debugging.
- **Wähle den richtigen Developer** — WhatsApp-Feature? Nutze `@whatsapp-dev`, nicht `@general-dev`
- **Parallelisiere wenn möglich** — z.B. `@bd + @ux` oder `@whatsapp-dev + @face-recognition-dev` gleichzeitig
- **Lass Tester blockieren** — wenn Tests rot sind, merged nichts.
- **QS nach jedem größeren Feature** — Log-Analyse verhindert, dass Bugs in Production gehen.
- **Scribe am Ende** — nicht während Entwicklung, sonst veraltet Doku sofort.

## Vorteile des Feature-basierten Setups

✅ **Fokussierter Kontext**: Jeder Developer kennt nur seine Domain → weniger Token-Verbrauch
✅ **Tieferes Verständnis**: Spezialisierung auf wenige Dateien → bessere Code-Qualität
✅ **Parallele Arbeit**: 3-4 Developer arbeiten gleichzeitig an verschiedenen Features
✅ **Wiederverwendbar**: WhatsApp-Dev kann für alle WhatsApp-Features genutzt werden
✅ **Keine Konflikte**: Klare File-Ownership → keine Race Conditions
