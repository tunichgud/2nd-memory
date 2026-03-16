/**
 * test_security_structural.js – Strukturelle Sicherheitstests (Anti-Tamper)
 *
 * Abgedeckte Test-IDs:
 *   AT-SEC-030  /api/whatsapp/send MUSS assertSendAllowed aufrufen (Quellcode-Analyse)
 *   AT-SEC-040  Jeder sendMessage-Aufruf ist durch assertSendAllowed geschuetzt
 *   AT-SEC-041  assertSendAllowed ist als module.exports exponiert
 *   AT-SEC-042  assertSendAllowed fuehrt strikte Gleichheitspruefung durch
 *
 * Testmethode: Strukturelle Quellcode-Analyse via fs.readFileSync.
 * Diese Tests koennen NICHT durch Aendern der Laufzeitlogik umgangen werden --
 * der Quellcode selbst wird geprueft.
 *
 * Ausfuehren: node tests/whatsapp/test_security_structural.js
 */

'use strict';

const fs = require('fs');
const path = require('path');

let passed = 0;
let failed = 0;

function pass(desc) {
    console.log(`  PASS: ${desc}`);
    passed++;
}

function fail(desc, detail) {
    console.error(`  FAIL: ${desc}${detail ? ' -- ' + detail : ''}`);
    failed++;
}

function assert(desc, condition, detail) {
    if (condition) {
        pass(desc);
    } else {
        fail(desc, detail || '');
    }
}

// Lade index.js Quellcode
const INDEX_JS_PATH = path.resolve(__dirname, '../../index.js');
const source = fs.readFileSync(INDEX_JS_PATH, 'utf8');
const lines = source.split('\n');

console.log('\n=== Strukturelle Sicherheitstests (Anti-Tamper) ===\n');

// ---------------------------------------------------------------------------
// AT-SEC-041: assertSendAllowed ist als module.exports exponiert
// ---------------------------------------------------------------------------
console.log('AT-SEC-041: assertSendAllowed in module.exports:');
{
    const hasExport = source.includes('module.exports') && source.includes('assertSendAllowed');
    assert(
        'module.exports enthaelt assertSendAllowed',
        hasExport,
        'Ohne Export koennen Tests die echte Funktion nicht importieren'
    );

    // Praezisere Pruefung: module.exports = { assertSendAllowed ... }
    const exportMatch = source.match(/module\.exports\s*=\s*\{[^}]*assertSendAllowed[^}]*\}/);
    assert(
        'module.exports-Block enthaelt assertSendAllowed als benanntes Export',
        exportMatch !== null,
        'assertSendAllowed muss explizit in module.exports stehen'
    );
}

// ---------------------------------------------------------------------------
// AT-SEC-042: assertSendAllowed fuehrt strikte Gleichheitspruefung durch
// ---------------------------------------------------------------------------
console.log('\nAT-SEC-042: Strikte Gleichheitspruefung in assertSendAllowed:');
{
    // Finde den Funktionskoerper von assertSendAllowed
    const fnMatch = source.match(/function assertSendAllowed[\s\S]*?^}/m);
    const fnBody = fnMatch ? fnMatch[0] : '';

    if (!fnBody) {
        fail('assertSendAllowed Funktionskoerper gefunden', 'Funktion nicht lokalisierbar');
    } else {
        // Muss === oder !== verwenden
        const hasStrictEquals = fnBody.includes('===') || fnBody.includes('!==');
        assert(
            'assertSendAllowed verwendet === oder !== (strikter Vergleich)',
            hasStrictEquals,
            'Strikte Gleichheit erforderlich um Type-Coercion zu verhindern'
        );

        // Darf NICHT == oder != verwenden (ausser als Teil von === oder !==)
        // Entferne === und !== und pruefe ob noch == oder != vorhanden
        const bodyWithoutStrict = fnBody.replace(/!==|===/g, '');
        const hasLooseEquals = /[^!<>]==[^=]/.test(bodyWithoutStrict) ||
                               /[^!]!=[^=]/.test(bodyWithoutStrict);
        assert(
            'assertSendAllowed verwendet KEIN == oder != (lose Gleichheit)',
            !hasLooseEquals,
            'Lose Gleichheit koennte durch Type Coercion umgangen werden'
        );

        // Darf KEINE RegExp oder .includes() fuer Chat-ID-Vergleich verwenden
        const hasRegExpInGuard = fnBody.includes('RegExp') || fnBody.includes('.test(');
        const hasIncludesInGuard = fnBody.includes('.includes(');
        assert(
            'assertSendAllowed verwendet KEIN RegExp fuer Chat-ID-Vergleich',
            !hasRegExpInGuard,
            'RegExp-Vergleiche koennen umgangen werden'
        );
        assert(
            'assertSendAllowed verwendet KEIN .includes() fuer Chat-ID-Vergleich',
            !hasIncludesInGuard,
            '.includes()-Vergleiche sind nicht exakt genug'
        );
    }
}

// ---------------------------------------------------------------------------
// AT-SEC-030: /api/whatsapp/send MUSS assertSendAllowed aufrufen
// ---------------------------------------------------------------------------
console.log('\nAT-SEC-030: /api/whatsapp/send ruft assertSendAllowed auf:');
{
    // Finde den POST /api/whatsapp/send Handler
    const handlerMatch = source.match(
        /app\.post\(['"]\/api\/whatsapp\/send['"][\s\S]*?(?=\n(?:\/\/|app\.|module\.))/
    );

    if (!handlerMatch) {
        fail('POST /api/whatsapp/send Handler gefunden', 'Handler nicht lokalisierbar');
    } else {
        const handlerBody = handlerMatch[0];

        // assertSendAllowed muss im Handler vorkommen
        const hasGuard = handlerBody.includes('assertSendAllowed');
        assert(
            'POST /api/whatsapp/send ruft assertSendAllowed auf',
            hasGuard,
            'SICHERHEITSLUECKE: Kein assertSendAllowed im Handler!'
        );

        // assertSendAllowed muss VOR sendMessage stehen
        const guardIdx = handlerBody.indexOf('assertSendAllowed');
        const sendIdx = handlerBody.indexOf('sendMessage');
        if (hasGuard && sendIdx !== -1) {
            assert(
                'assertSendAllowed wird VOR sendMessage aufgerufen',
                guardIdx < sendIdx,
                `assertSendAllowed bei Index ${guardIdx}, sendMessage bei ${sendIdx}`
            );
        }
    }
}

// ---------------------------------------------------------------------------
// AT-SEC-040: Jeder sendMessage/reply-Aufruf ist durch Guard geschuetzt
// ---------------------------------------------------------------------------
console.log('\nAT-SEC-040: Vollstaendigkeits-Check aller Send-Pfade:');
{
    /**
     * Analysiert alle Zeilen auf sendMessage und .reply( Aufrufe.
     * Fuer jeden Aufruf wird geprueft, ob in der zugehoerigen Funktion/
     * dem zugehoerigen Handler ein assertSendAllowed-Aufruf steht
     * ODER ob er durch den 4-Stufen-Guard (msg.from === user_chat_id &&
     * msg.id.remote === user_chat_id) geschuetzt ist.
     */

    // Finde alle Zeilen mit sendMessage oder .reply(
    const sendLines = [];
    lines.forEach((line, idx) => {
        // client.sendMessage( oder chat.sendMessage( oder .reply(
        if (/client\.sendMessage\(|chat\.sendMessage\(|msg\.reply\(/.test(line)) {
            sendLines.push({ lineNum: idx + 1, line: line.trim() });
        }
    });

    assert(
        `${sendLines.length} Send-Aufrufe in index.js gefunden`,
        sendLines.length > 0,
        'Keine sendMessage/reply-Aufrufe gefunden?'
    );

    // Fuer jeden Send-Aufruf pruefen ob er geschuetzt ist
    let allGuarded = true;
    sendLines.forEach(({ lineNum, line }) => {
        // Hole Kontext: 200 Zeilen vor diesem Aufruf (Funktionskoerper)
        const contextStart = Math.max(0, lineNum - 200);
        const contextLines = lines.slice(contextStart, lineNum);
        const context = contextLines.join('\n');

        // Pruefung 1: assertSendAllowed im Kontext
        const hasAssertSend = context.includes('assertSendAllowed');

        // Pruefung 2: 4-Stufen-Guard fuer msg.reply() (Zeile 275)
        // Der Guard prueft msg.from === user_chat_id && msg.id.remote === user_chat_id
        const hasFourStepGuard = (
            line.includes('msg.reply(') && (
                context.includes('msg.from !== BOT_CONFIG.user_chat_id') ||
                context.includes('msg.id.remote !== BOT_CONFIG.user_chat_id') ||
                (context.includes('msg.from') && context.includes('user_chat_id'))
            )
        );

        const isGuarded = hasAssertSend || hasFourStepGuard;

        if (!isGuarded) {
            allGuarded = false;
            console.error(`    UNGUARDED: Zeile ${lineNum}: ${line}`);
            console.error(`    -> Kein assertSendAllowed und kein 4-Stufen-Guard gefunden!`);
        } else {
            const guardType = hasAssertSend ? 'assertSendAllowed' : '4-Stufen-Guard';
            console.log(`    OK: Zeile ${lineNum}: ${line.substring(0, 60)} [${guardType}]`);
        }
    });

    assert(
        'Alle Send-Aufrufe sind durch Guard geschuetzt',
        allGuarded,
        'Mindestens ein ungeschuetzter Send-Pfad gefunden!'
    );
}

// ---------------------------------------------------------------------------
// Zusammenfassung
// ---------------------------------------------------------------------------

console.log('\n' + '='.repeat(60));
console.log(`Ergebnis: ${passed} Tests bestanden, ${failed} Tests fehlgeschlagen`);
console.log('='.repeat(60) + '\n');

if (failed > 0) {
    console.error('FEHLER: Strukturelle Sicherheitstests fehlgeschlagen!');
    console.error('   MERGE BLOCKIERT: Sicherheitsluecke im Send-Guard!');
    process.exit(1);
} else {
    console.log('ERFOLG: Alle strukturellen Sicherheitstests bestanden.');
    console.log('Alle Send-Pfade sind durch Guards geschuetzt.');
    process.exit(0);
}
