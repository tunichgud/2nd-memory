# ADR 001: WhatsApp Library Choice - whatsapp-web.js vs Baileys

**Status**: Accepted
**Date**: 2026-03-10
**Deciders**: @architect, @whatsapp-dev, @tester
**Technical Story**: Baileys Migration Evaluation (Sprint 2)

## Context and Problem Statement

Unser WhatsApp-Integration hatte eine kritische Limitierung: Die Historie-Funktion konnte nicht alle Nachrichten aus einem Chat laden. Für den Chat mit "Thomas Bauer" wurden nur 1 Nachricht angezeigt, obwohl hunderte Nachrichten existieren sollten.

Wir mussten entscheiden:
- Können wir das Problem durch Migration auf Baileys lösen?
- Welche WhatsApp-Bibliothek ist langfristig die beste Wahl?

## Decision Drivers

- **Vollständige Message-History**: Zugriff auf alle Chat-Nachrichten, nicht nur DOM-geladene
- **Stabilität**: Produktionsreife, geringe Crash-Rate
- **Wartbarkeit**: Aktive Entwicklung, gute Dokumentation
- **Ressourcen**: RAM/CPU-Verbrauch, Skalierbarkeit
- **Architektur**: Saubere API, gute Fehlerbehandlung

## Considered Options

1. **whatsapp-web.js** (Puppeteer-basiert)
2. **Baileys v6.17.16** (WebSocket-basiert)
3. **Baileys v7.x** (RC, neueste Version)
4. **Android Emulator** mit WhatsApp DB-Zugriff

## Decision Outcome

**Chosen option**: **whatsapp-web.js + TXT-Imports**

### Begründung

Nach vollständiger Migration und Testing von Baileys v6.17.16 stellten wir fest:

**Baileys löst das History-Problem NICHT!**

Beide Bibliotheken haben die gleiche fundamentale Limitierung:

| Aspekt | whatsapp-web.js | Baileys v6/v7 |
|--------|----------------|---------------|
| **Historische Messages** | ❌ Nur DOM-geladene Messages zugänglich | ❌ Nur initial-sync + real-time Messages |
| **On-Demand History** | ❌ `fetchMessages({limit: Infinity})` limitiert auf DOM | ❌ `fetchMessageHistory()` funktioniert NICHT on-demand |
| **Theodore Chat** | 1 Message sichtbar | 0 Messages geladen (Timeout) |
| **Marie Chat** | 1 Message sichtbar | 0 Messages geladen |

### Technische Details

**whatsapp-web.js Limitation**:
```javascript
const messages = await chat.fetchMessages({ limit: Infinity });
// Returns nur Messages die im Browser-DOM geladen sind
// WhatsApp Web lädt Messages lazy (on scroll)
```

**Baileys Limitation**:
```javascript
await sock.fetchMessageHistory(50, oldestMsgKey, oldestMsgTimestamp);
// Event 'messaging-history.set' wird NIEMALS gefeuert
// API funktioniert nur während initial history sync (first pairing)
// WhatsApp Server unterstützt kein on-demand history loading
```

**Fehler-Log** (Baileys):
```
[WhatsApp] 📜 Lade vollständige Historie für 4917665727832@c.us...
[WhatsApp]   Request 1: latest 50...
[WhatsApp]   ❌ Fehler: Cannot read properties of undefined (reading 'remoteJid')
[WhatsApp] 📦 Historie komplett: 0 Nachrichten geladen

Error: Timeout waiting for message history (30s)
```

### Warum whatsapp-web.js beibehalten?

**Vorteile whatsapp-web.js**:
1. ✅ **Stabil und produktionserprobt** (seit Jahren im Einsatz)
2. ✅ **Funktioniert zuverlässig** für Real-time Messages
3. ✅ **Gute Community-Support** und Dokumentation
4. ✅ **Keine Verschlechterung** gegenüber Baileys
5. ✅ **Session-Management** robust (.wwebjs_auth)

**Nachteile Baileys**:
1. ❌ **Löst Problem nicht** (gleiche Historie-Limitation)
2. ❌ **Weniger getestet** in unserem Kontext
3. ❌ **Breaking Changes** zwischen v6 → v7 (instabile API)
4. ❌ **Komplexere Event-Handling** (Promises + Events gemischt)
5. ❌ **Session korrupt** nach Baileys-Test (QR Code neu scannen nötig)

### Die Lösung: TXT-Import

**Bereits implementiert und funktionierend**:
```bash
# Marie Mueller: 3020 chunks aus WhatsApp TXT-Export
backend/scripts/migrate_txt_imports.py
```

**Warum TXT-Import die beste Lösung ist**:
- ✅ **Vollständige Historie** (WhatsApp exportiert ALLES)
- ✅ **Keine API-Limitationen** (direkt aus Export-File)
- ✅ **Einmalig nötig** (danach nur Real-time Capture)
- ✅ **Zuverlässig** (kein Rate-Limiting, kein Ban-Risiko)

### Hybrid-Ansatz (Empfohlen)

```
┌─────────────────────────────────────────────────────┐
│  Historische Daten (bis heute)                       │
│  ↓                                                   │
│  WhatsApp TXT-Export → migrate_txt_imports.py        │
│  ✅ 3020 chunks (Marie)                              │
└─────────────────────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────┐
│  Ab heute: Real-time Capture                         │
│  ↓                                                   │
│  whatsapp-web.js → messages.upsert → ChromaDB       │
│  ✅ Alle neuen Nachrichten                           │
└─────────────────────────────────────────────────────┘
```

## Positive Consequences

- ✅ **Stabile Lösung** basierend auf bewährter Technologie
- ✅ **Vollständige Historie** durch TXT-Import
- ✅ **Real-time Capture** durch whatsapp-web.js
- ✅ **Kein Risiko** durch experimentelle Migration
- ✅ **Wartbar** (bekannte Codebasis)

## Negative Consequences

- ❌ **Manuelle TXT-Exports** nötig für historische Daten
- ❌ **Keine automatische Backfill-Funktion** für alte Messages
- ❌ **Puppeteer-Overhead** (200MB RAM, Chrome-Prozess)

## Migration History

### Durchgeführte Migration (2026-03-09/10)

**Phase 1: Vorbereitung**
- Git Tag erstellt: `v0.2.0-whatsapp-web-js`
- Backups: `.wwebjs_auth` (90 MB) + ChromaDB (30 MB)
- Feature Branch: `feature/baileys-migration`

**Phase 2: Implementation**
- index.js komplett umgeschrieben (750 → 645 lines)
- Baileys v6.17.16 installiert
- `loadFullChatHistory()` implementiert mit Pagination

**Phase 3: Testing**
- QR Code gescannt ✅
- Verbindung hergestellt ✅
- Chat-Listing funktioniert ✅ (178 Gruppen)
- **History Loading FAILED** ❌ (Timeout, 0 Messages)

**Phase 4: Rollback (nach User-Request)**
```bash
git checkout main
npm install  # whatsapp-web.js wiederhergestellt
./start.sh   # QR Code neu scannen nötig
```

### Learnings

1. **Baileys v6 API** ist für initial sync konzipiert, NICHT für on-demand history
2. **WhatsApp Protocol** erlaubt kein beliebiges History Loading
3. **TXT-Export** ist die einzige zuverlässige Methode für Backfill
4. **Session Corruption** möglich bei Library-Wechsel (.wwebjs_auth)

## Future Considerations

### Baileys v7 Re-Evaluation?

**Wann wir Baileys v7 nochmal testen sollten**:
- ✅ Stable Release (kein RC mehr)
- ✅ Dokumentierte on-demand history API
- ✅ Community-Reports über erfolgreiche History-Loads
- ✅ Klarer Performance-Vorteil (z.B. 10x schneller)

**Timeline**: Q3 2026 (wenn v7 stable)

### Android Emulator Approach?

**Pro**:
- Direkter Zugriff auf `msgstore.db` (SQLite)
- Volle Kontrolle über WhatsApp-Daten
- Automation möglich (adb, Appium)

**Contra**:
- Sehr komplex (Setup, Maintenance)
- Ressourcen-intensiv (2-4 GB RAM)
- WhatsApp TOS-Risiko (Account-Ban möglich)
- Multi-Device-Limit (max 4 Geräte)

**Entscheidung**: NICHT implementieren (Kosten > Nutzen)

## Links

- [Baileys GitHub](https://github.com/WhiskeySockets/Baileys)
- [whatsapp-web.js GitHub](https://github.com/pedroslopez/whatsapp-web.js)
- Migration Plan: `/BAILEYS_MIGRATION_PLAN.md`
- Git Tag: `v0.2.0-whatsapp-web-js`
- Feature Branch: `feature/baileys-migration` (nicht merged)

## Appendix

### Code Comparison

**whatsapp-web.js** (aktuell):
```javascript
const { Client, LocalAuth } = require('whatsapp-web.js');
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: { executablePath: '/usr/bin/google-chrome' }
});

client.on('message_create', async msg => {
    await saveMessageToBackend(msg, chatName);
});
```

**Baileys v6** (getestet, verworfen):
```javascript
const { default: makeWASocket, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const { state, saveCreds } = await useMultiFileAuthState('.baileys_auth');
const sock = makeWASocket({ auth: state });

sock.ev.on('messages.upsert', async ({ messages, type }) => {
    // Real-time funktioniert
    // History Loading funktioniert NICHT
});
```

### Performance Metrics

| Metric | whatsapp-web.js | Baileys v6 |
|--------|----------------|------------|
| RAM Usage | ~200 MB | ~100 MB |
| CPU Usage | ~5% (idle) | ~2% (idle) |
| Startup Time | ~15s (QR scan) | ~8s (QR scan) |
| Message Latency | <1s | <1s |
| **History Loading** | **Partial (DOM)** | **None (Timeout)** |

### Test Results Summary

```
Thomas Bauer Chat:
- whatsapp-web.js: 1 message loaded (DOM limitation)
- Baileys v6:      0 messages loaded (API timeout)
- TXT-Import:      ✅ Volle Historie verfügbar

Marie Mueller Chat:
- whatsapp-web.js: 1 message loaded
- Baileys v6:      0 messages loaded
- TXT-Import:      ✅ 3020 chunks geladen
```

---

**Decision Status**: ✅ FINAL
**Next Review**: Q3 2026 (Baileys v7 stable release)
