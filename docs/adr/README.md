# Architecture Decision Records (ADR)

Dieses Verzeichnis enthält alle wichtigen Architektur-Entscheidungen für das 2nd-Memory-Projekt.

## Was ist ein ADR?

Ein **Architecture Decision Record** (ADR) dokumentiert eine wichtige Architektur-Entscheidung zusammen mit ihrem Kontext und ihren Konsequenzen.

ADRs helfen dabei:
- ✅ Entscheidungen nachvollziehbar zu machen
- ✅ Wissen im Team zu teilen
- ✅ Diskussionen zu strukturieren
- ✅ Fehler zu vermeiden (aus alten Learnings lernen)

## Format

Wir verwenden das [MADR Format](https://adr.github.io/madr/) (Markdown Architecture Decision Records):

```markdown
# ADR {NUMBER}: {TITLE}

**Status**: {Proposed | Accepted | Deprecated | Superseded}
**Date**: YYYY-MM-DD
**Deciders**: @person1, @person2
**Technical Story**: Link oder Beschreibung

## Context and Problem Statement
Welches Problem lösen wir?

## Decision Drivers
Welche Faktoren beeinflussen die Entscheidung?

## Considered Options
1. Option A
2. Option B
3. Option C

## Decision Outcome
Gewählte Option + Begründung

## Positive Consequences
Was wird besser?

## Negative Consequences
Was sind die Nachteile?

## Links
Relevante Dokumentation
```

## Alle ADRs

| # | Titel | Status | Datum | Thema |
|---|-------|--------|-------|-------|
| [001](./001-whatsapp-library-choice.md) | WhatsApp Library Choice (whatsapp-web.js vs Baileys) | ✅ Accepted | 2026-03-10 | WhatsApp Integration |

## Wann ein ADR schreiben?

Erstelle ein ADR bei:
- **Technologie-Wechsel** (z.B. Library-Migration)
- **Architektur-Entscheidungen** (z.B. Monolith vs Microservices)
- **Design-Pattern-Wahl** (z.B. Event-driven vs Request-Response)
- **Infrastruktur-Entscheidungen** (z.B. Cloud-Provider, Deployment-Strategie)
- **Security-Entscheidungen** (z.B. Auth-Methode, Encryption)

**Faustregel**: Wenn die Entscheidung in 6 Monaten schwer nachvollziehbar wäre → ADR!

## Workflow

1. **Proposal**: Erstelle Draft-ADR mit Status "Proposed"
2. **Review**: Team diskutiert (z.B. im PR)
3. **Decision**: Status → "Accepted" oder "Rejected"
4. **Updates**: Bei Änderungen Status → "Deprecated" oder "Superseded"

## Beispiel-Workflow

```bash
# 1. Neues ADR erstellen
touch docs/adr/002-database-choice.md

# 2. Template ausfüllen
# ... (siehe Format oben)

# 3. Commit & PR
git add docs/adr/002-database-choice.md
git commit -m "docs: add ADR 002 - Database Choice"

# 4. Nach Review: Status auf "Accepted" setzen
```

## Templates

- [MADR Template](https://adr.github.io/madr/)
- [ADR Tools](https://github.com/npryce/adr-tools)

## Best Practices

1. **Kurz & prägnant** (1-2 Seiten max)
2. **Kontext zuerst** (warum entscheiden wir?)
3. **Optionen auflisten** (nicht nur die gewählte!)
4. **Konsequenzen klar benennen** (positiv UND negativ)
5. **Links zu Ressourcen** (Docs, Issues, PRs)
6. **Zeitstempel** (wann wurde entschieden?)
7. **Status aktuell halten** (Deprecated kennzeichnen)

## Anti-Patterns

❌ **Nicht tun**:
- Implementierungs-Details dokumentieren (gehört in Code-Kommentare)
- Triviale Entscheidungen ("We use JSON for config")
- Entscheidungen nachträglich rechtfertigen (be honest!)
- ADRs löschen (statt auf "Deprecated" setzen)

## History

- **2026-03-10**: ADR 001 - WhatsApp Library Choice (Baileys Rollback)
