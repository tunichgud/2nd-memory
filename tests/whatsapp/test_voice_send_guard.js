/**
 * test_voice_send_guard.js – Node.js Safety Tests fuer assertSendAllowed + handleVoiceMessage
 *
 * MERGE-BLOCKER: Alle Tests muessen PASS sein.
 * Prueft:
 *   - assertSendAllowed() wirft bei fremder Chat-ID
 *   - assertSendAllowed() wirft wenn user_chat_id nicht gesetzt
 *   - assertSendAllowed() erlaubt eigene Chat-ID ohne Fehler
 *   - handleVoiceMessage ruft assertSendAllowed auf (struktureller Test via Quellcode-Analyse)
 *
 * Ausfuehren: node tests/whatsapp/test_voice_send_guard.js
 */

'use strict';

// Setze WHATSAPP_PORT auf einen freien Port bevor index.js geladen wird,
// damit kein EADDRINUSE-Fehler entsteht wenn der echte Port 3001 belegt ist.
// index.js liest: const PORT = process.env.WHATSAPP_PORT || 3001;
process.env.WHATSAPP_PORT = process.env.WHATSAPP_PORT || '0';

const path = require('path');
const fs = require('fs');
const { assertSendAllowed } = require('../../index.js');

let passed = 0;
let failed = 0;

// ─── Test-Helfer ──────────────────────────────────────────────────────────────

function pass(desc) {
    console.log(`  PASS: ${desc}`);
    passed++;
}

function fail(desc, detail) {
    console.error(`  FAIL: ${desc}${detail ? ' -- ' + detail : ''}`);
    failed++;
}

/**
 * Erwartet dass fn() einen Error wirft, optional mit erwartetem Fragment.
 * @param {string} desc
 * @param {Function} fn
 * @param {string} [expectedFragment]
 */
function assertThrows(desc, fn, expectedFragment) {
    try {
        fn();
        fail(desc, 'Kein Error geworfen');
    } catch (err) {
        if (expectedFragment && !err.message.includes(expectedFragment)) {
            fail(desc, `Error-Message "${err.message}" enthaelt nicht "${expectedFragment}"`);
        } else {
            pass(desc + (expectedFragment ? ` -> "${err.message}"` : ''));
        }
    }
}

/**
 * Erwartet dass fn() KEINEN Error wirft.
 * @param {string} desc
 * @param {Function} fn
 */
function assertNoThrow(desc, fn) {
    try {
        fn();
        pass(desc);
    } catch (err) {
        fail(desc, `Unerwarteter Error: "${err.message}"`);
    }
}

// ─── Test-Fixtures ────────────────────────────────────────────────────────────

const MY_CHAT_ID    = '491701234567@c.us';
const SARAH_CHAT_ID = '491709876543@c.us';
const GROUP_CHAT_ID = '123456789@g.us';

const CONFIG_OK    = { user_chat_id: MY_CHAT_ID };
const CONFIG_NULL  = { user_chat_id: null };
const CONFIG_EMPTY = { user_chat_id: '' };

// ─── Tests ────────────────────────────────────────────────────────────────────

console.log('\n=== Voice Send Guard Safety Tests ===\n');

// 1. Fremde Chat-ID wird blockiert
console.log('1. Fremde Chat-ID blockieren:');
assertThrows(
    'assertSendAllowed wirft bei fremder ID (Sarah)',
    () => assertSendAllowed(SARAH_CHAT_ID, CONFIG_OK),
    'Safety:'
);
assertThrows(
    'assertSendAllowed wirft bei Gruppen-Chat-ID',
    () => assertSendAllowed(GROUP_CHAT_ID, CONFIG_OK),
    'Safety:'
);

// 2. Eigene Chat-ID erlaubt
console.log('\n2. Eigene Chat-ID erlauben:');
assertNoThrow(
    'assertSendAllowed erlaubt eigene Chat-ID ohne Error',
    () => assertSendAllowed(MY_CHAT_ID, CONFIG_OK)
);

// 3. user_chat_id nicht konfiguriert
console.log('\n3. user_chat_id nicht konfiguriert:');
assertThrows(
    'assertSendAllowed wirft wenn user_chat_id === null',
    () => assertSendAllowed(MY_CHAT_ID, CONFIG_NULL),
    'Safety:'
);
assertThrows(
    'assertSendAllowed wirft wenn user_chat_id === "" (leerer String)',
    () => assertSendAllowed(MY_CHAT_ID, CONFIG_EMPTY),
    'Safety:'
);
assertThrows(
    'assertSendAllowed wirft bei fremder ID UND null-Config',
    () => assertSendAllowed(SARAH_CHAT_ID, CONFIG_NULL),
    'Safety:'
);

// 4. Error-Message-Format fuer HTTP-403-Erkennung
console.log('\n4. Error-Message Format:');
{
    let msg = null;
    try { assertSendAllowed(SARAH_CHAT_ID, CONFIG_OK); } catch (e) { msg = e.message; }
    if (msg && msg.startsWith('Safety:')) {
        pass('Error-Message beginnt mit "Safety:" (noetig fuer 403-Erkennung im Endpoint)');
    } else {
        fail('Error-Message beginnt mit "Safety:"', `Tatsaechlich: "${msg}"`);
    }
    if (msg && msg.includes(SARAH_CHAT_ID)) {
        pass(`Error-Message nennt geblockte ID "${SARAH_CHAT_ID}"`);
    } else {
        fail(`Error-Message nennt geblockte ID "${SARAH_CHAT_ID}"`, `Tatsaechlich: "${msg}"`);
    }
}

// 5. Struktureller Test: handleVoiceMessage ruft assertSendAllowed auf
console.log('\n5. Struktureller Test: handleVoiceMessage ruft assertSendAllowed auf:');
{
    const indexSource = fs.readFileSync(
        path.resolve(__dirname, '../../index.js'),
        'utf8'
    );
    // Pruefe dass assertSendAllowed innerhalb von handleVoiceMessage vorkommt
    const fnMatch = indexSource.match(/async function handleVoiceMessage[\s\S]*?^}/m);
    if (fnMatch) {
        const fnBody = fnMatch[0];
        if (fnBody.includes('assertSendAllowed')) {
            pass('handleVoiceMessage enthaelt assertSendAllowed-Aufruf');
        } else {
            fail('handleVoiceMessage muss assertSendAllowed aufrufen', 'Nicht gefunden in Funktionskoerper');
        }
    } else {
        // Fallback: pruefe ob beide Bezeichner in der Naehe voneinander vorkommen
        const hvmIdx = indexSource.indexOf('handleVoiceMessage');
        const asaIdx = indexSource.indexOf('assertSendAllowed', hvmIdx);
        // Erlaube bis zu 3000 Zeichen Abstand (Funktionskoerper)
        if (hvmIdx !== -1 && asaIdx !== -1 && (asaIdx - hvmIdx) < 3000) {
            pass('handleVoiceMessage gefolgt von assertSendAllowed-Aufruf innerhalb 3000 Zeichen');
        } else {
            fail('handleVoiceMessage muss assertSendAllowed aufrufen', 'Nicht in erwartetem Abstand gefunden');
        }
    }
}

// 6. Edge Cases
console.log('\n6. Edge Cases:');
assertThrows(
    'assertSendAllowed wirft bei chatId === undefined',
    () => assertSendAllowed(undefined, CONFIG_OK),
    'Safety:'
);
assertThrows(
    'assertSendAllowed wirft bei chatId === "" (leerer String)',
    () => assertSendAllowed('', CONFIG_OK),
    'Safety:'
);
assertThrows(
    'assertSendAllowed wirft bei chatId === null',
    () => assertSendAllowed(null, CONFIG_OK),
    'Safety:'
);

// ─── Zusammenfassung ──────────────────────────────────────────────────────────

console.log('\n' + '='.repeat(60));
console.log(`Ergebnis: ${passed} Tests bestanden, ${failed} Tests fehlgeschlagen`);
console.log('='.repeat(60) + '\n');

if (failed > 0) {
    console.error('FEHLER: Voice Send Guard ist nicht korrekt implementiert!');
    console.error('   MERGE BLOCKIERT: Nachrichten koennten an unberechtigte Empfaenger gesendet werden.');
    process.exit(1);
} else {
    console.log('ERFOLG: Voice Send Guard schuetzt vor unberechtigtem Senden.');
    console.log('Memosaur sendet Sprachnachrichten-Zusammenfassungen nur an den eigenen Chat.');
}
