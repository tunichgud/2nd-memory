# Multi-Agent Setup für Antigravity
## Node.js + Python Full-Stack · Claude Sonnet

---

## Übersicht

Dieses Setup definiert **8 spezialisierte Agenten** für den **Antigravity Manager View**.
Jeder Agent hat eine klare Rolle und Übergabepunkte an den nächsten.

```
Feature Request
      │
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
    │REFACTORER │                   │  SCRIBE   │
    │(Thinking) │                   │ (Standard)│
    └───────────┘                   └───────────┘
```

### Agent-Domains

**Planning:** Architect (1)
**Implementation:** 4 Feature-Developers (parallel execution möglich)
  - `@whatsapp-dev`: WhatsApp, Import, Bot
  - `@face-recognition-dev`: Face Detection, Clustering, Entities
  - `@chat-rag-dev`: Chat UI, RAG Pipeline, LLM
  - `@general-dev`: Infrastructure, Config, Media, Maps

**Quality:** Tester (1)
**Maintenance:** Refactorer (1) + Scribe (1)

---

## Installation

1. Diesen `.antigravity/` Ordner in dein **Projekt-Root** kopieren
2. Antigravity öffnen → Manager View
3. Agenten über die Prompt-Eingabe aufrufen (siehe unten)

---

## Agenten aufrufen

### Im Manager View — neue Mission starten:

**Architect** (immer zuerst bei neuen Features):
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

**Refactorer** (on-demand):
```
@refactorer Analysiere [module/file] auf Refactoring-Potenzial.
```

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
| Tester + Scribe | Tests schreiben während Docs entstehen |
| Architect (Feature A) + Developer (Feature B) | Planung läuft vor, Implementation folgt |
| WhatsApp-Dev + Face-Recognition-Dev | Unabhängige Domains, keine File-Konflikte |
| Chat-RAG-Dev + General-Dev | Backend vs. Frontend/Infrastructure |
| Refactorer + Scribe | Code verbessern + dokumentieren gleichzeitig |

**Nicht parallel:**
- Architect + Developer am gleichen Feature (Developer wartet auf Plan)
- Zwei Developers auf derselben Datei (Race condition)
- WhatsApp-Dev + General-Dev auf `backend/main.py` (Router registration conflict)

---

## Modell-Konfiguration

| Agent | Modus | Warum |
|-------|-------|-------|
| Architect | Sonnet Thinking | Braucht tiefes Reasoning für Planung |
| WhatsApp-Dev | Sonnet Standard | Feature-fokussiert, klare Patterns |
| Face-Recognition-Dev | Sonnet Standard | CV-Algorithmen, numerische Arbeit |
| Chat-RAG-Dev | Sonnet Standard | RAG-Pipeline, bekannte Patterns |
| General-Dev | Sonnet Standard | Infrastructure, repetitive Tasks |
| Tester | Sonnet Standard | Regelbasiert, kein Deep Thinking nötig |
| Refactorer | Sonnet Thinking | Braucht Analyse über mehrere Dateien |
| Scribe | Sonnet Standard | Dokumentation ist repetitiv |

---

## Dateien in diesem Setup

```
.antigravity/
├── README.md                    ← Diese Datei
├── rules.md                     ← Globale Regeln (alle Agenten lesen das)
├── architect.md                 ← Planungs-Agent
├── whatsapp-dev.md             ← WhatsApp Feature Developer
├── face-recognition-dev.md     ← Face Recognition Developer
├── chat-rag-dev.md             ← Chat & RAG Developer
├── general-dev.md              ← General Infrastructure Developer
├── tester.md                   ← Test-Agent
├── refactorer.md               ← Refactoring-Agent
├── scribe.md                   ← Dokumentations-Agent
└── coder.md                    ← Legacy (ersetzt durch 4 Feature-Devs)
```

---

## Tipps

- **Starte immer mit Architect** — auch für kleine Features. 2 Minuten Planung spart 20 Minuten Debugging.
- **Wähle den richtigen Developer** — WhatsApp-Feature? Nutze `@whatsapp-dev`, nicht `@general-dev`
- **Parallelisiere wenn möglich** — z.B. `@whatsapp-dev` + `@face-recognition-dev` gleichzeitig
- **Lass Tester blockieren** — wenn Tests rot sind, merged nichts.
- **Scribe am Ende** — nicht während Entwicklung, sonst veraltet Doku sofort.
- **Refactorer separat** — nie gleichzeitig mit neuen Features, sonst verlierst du den Überblick.

## Vorteile des Feature-basierten Setups

✅ **Fokussierter Kontext**: Jeder Developer kennt nur seine Domain → weniger Token-Verbrauch
✅ **Tieferes Verständnis**: Spezialisierung auf wenige Dateien → bessere Code-Qualität
✅ **Parallele Arbeit**: 3-4 Developer arbeiten gleichzeitig an verschiedenen Features
✅ **Wiederverwendbar**: WhatsApp-Dev kann für alle WhatsApp-Features genutzt werden
✅ **Keine Konflikte**: Klare File-Ownership → keine Race Conditions
