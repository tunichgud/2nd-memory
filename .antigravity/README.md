# Multi-Agent Setup für Antigravity
## Node.js + Python Full-Stack · Claude Sonnet

---

## Übersicht

Dieses Setup definiert 5 spezialisierte Agenten für den **Antigravity Manager View**.
Jeder Agent hat eine klare Rolle und Übergabepunkte an den nächsten.

```
Feature Request
      │
      ▼
┌─────────────┐
│  ARCHITECT  │  Plant · Spezifiziert · Fragt nach
│  (Thinking) │
└──────┬──────┘
       │ Approved Plan
       ▼
┌─────────────┐
│    CODER    │  Implementiert · Folgt Plan
│  (Standard) │
└──────┬──────┘
       │ Code fertig
       ▼
┌─────────────┐
│   TESTER    │  Testet · Blockiert bei Fehlern
│  (Standard) │
└──────┬──────┘
       │ Tests grün
       ▼
┌─────────────┐     ┌─────────────┐
│ REFACTORER  │     │   SCRIBE    │  (parallel möglich)
│  (Thinking) │     │  (Standard) │
└─────────────┘     └─────────────┘
```

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

**Coder** (nach Architect-Freigabe):
```
@coder Implementiere den Plan aus [Architect-Artifact]. Halte dich genau daran.
```

**Tester** (nach Coder):
```
@tester Schreibe und führe Tests für die Änderungen in [Files] aus.
```

**Refactorer** (on-demand):
```
@refactorer Analysiere [module/file] auf Refactoring-Potenzial.
```

**Scribe** (nach Feature-Completion):
```
@scribe Dokumentiere die Änderungen aus [Coder-Artifact] auf Deutsch und Englisch.
```

---

## Parallel-Workflows im Manager View

Antigravity erlaubt mehrere Agenten gleichzeitig. Sinnvolle Kombinationen:

| Parallel | Warum |
|----------|-------|
| Tester + Scribe | Tests schreiben während Docs entstehen |
| Architect (Feature A) + Coder (Feature B) | Planung läuft vor, Implementation folgt |
| Refactorer + Scribe | Code verbessern + dokumentieren gleichzeitig |

**Nicht parallel:**
- Architect + Coder am gleichen Feature (Coder wartet auf Plan)
- Zwei Coder auf derselben Datei (Race condition)

---

## Modell-Konfiguration

| Agent | Modus | Warum |
|-------|-------|-------|
| Architect | Sonnet Thinking | Braucht tiefes Reasoning für Planung |
| Coder | Sonnet Standard | Schnell, präzise Implementierung |
| Tester | Sonnet Standard | Regelbasiert, kein Deep Thinking nötig |
| Refactorer | Sonnet Thinking | Braucht Analyse über mehrere Dateien |
| Scribe | Sonnet Standard (Fast) | Dokumentation ist repetitiv |

---

## Dateien in diesem Setup

```
.antigravity/
├── rules.md              ← Globale Regeln (alle Agenten lesen das)
└── agents/
    ├── architect.md      ← Planungs-Agent
    ├── coder.md          ← Implementations-Agent
    ├── tester.md         ← Test-Agent
    ├── refactorer.md     ← Refactoring-Agent
    └── scribe.md         ← Dokumentations-Agent
```

---

## Tipps

- **Starte immer mit Architect** — auch für kleine Features. 2 Minuten Planung spart 20 Minuten Debugging.
- **Lass Tester blockieren** — wenn Tests rot sind, merged nichts.
- **Scribe am Ende** — nicht während Entwicklung, sonst veraltet Doku sofort.
- **Refactorer separat** — nie gleichzeitig mit neuen Features, sonst verlierst du den Überblick.
