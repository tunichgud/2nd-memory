/**
 * test_send_guard.js – Acceptance Test für den WhatsApp Send-Guard
 *
 * KONTEXT:
 * ========
 * Bug: Der /api/whatsapp/send Endpoint akzeptierte beliebige chatId-Werte
 *      und sendete Nachrichten an jeden Empfänger ohne Prüfung.
 *
 * Fix: assertSendAllowed(chatId, config) wird vor jedem sendMessage() aufgerufen.
 *      Die Funktion wirft einen Error wenn chatId !== user_chat_id.
 *      Der Endpoint gibt HTTP 403 zurück (kein 500) bei Safety-Fehlern.
 *
 * Dieser Test importiert assertSendAllowed() DIREKT aus index.js —
 * keine Logik-Kopie, kein Drift möglich.
 *
 * Ausführung: node tests/whatsapp/test_send_guard.js
 */

const { assertSendAllowed } = require('../../index.js');

let passed = 0;
let failed = 0;

/**
 * @param {string} description
 * @param {boolean} condition
 */
function assert(description, condition) {
    if (condition) {
        console.log(`  ✅ PASS: ${description}`);
        passed++;
    } else {
        console.error(`  ❌ FAIL: ${description}`);
        failed++;
    }
}

/**
 * Prüft dass assertSendAllowed() einen Error wirft.
 * @param {string} description
 * @param {string} chatId
 * @param {object} config
 * @param {string} [expectedFragment] - Optionaler Substring der im Error-Message erwartet wird
 */
function assertThrows(description, chatId, config, expectedFragment) {
    try {
        assertSendAllowed(chatId, config);
        console.error(`  ❌ FAIL: ${description} — kein Error geworfen`);
        failed++;
    } catch (err) {
        const messageOk = expectedFragment ? err.message.includes(expectedFragment) : true;
        if (messageOk) {
            console.log(`  ✅ PASS: ${description} → "${err.message}"`);
            passed++;
        } else {
            console.error(`  ❌ FAIL: ${description} — Error-Message enthält nicht "${expectedFragment}": "${err.message}"`);
            failed++;
        }
    }
}

/**
 * Prüft dass assertSendAllowed() KEINEN Error wirft.
 * @param {string} description
 * @param {string} chatId
 * @param {object} config
 */
function assertNoThrow(description, chatId, config) {
    try {
        assertSendAllowed(chatId, config);
        console.log(`  ✅ PASS: ${description}`);
        passed++;
    } catch (err) {
        console.error(`  ❌ FAIL: ${description} — unerwarteter Error: "${err.message}"`);
        failed++;
    }
}

// ─── Test-Fixtures ────────────────────────────────────────────────────────────

const MY_CHAT_ID    = '491701234567@c.us';
const SARAH_CHAT_ID = '491709876543@c.us';
const GROUP_CHAT_ID = '123456789@g.us';

const CONFIG_OK      = { user_chat_id: MY_CHAT_ID };
const CONFIG_NO_ID   = { user_chat_id: null };
const CONFIG_EMPTY   = { user_chat_id: '' };

// ─── Tests ────────────────────────────────────────────────────────────────────

console.log('\n=== WhatsApp Send-Guard Acceptance Tests ===\n');

// 1. Erlaubter Fall: eigener Chat
console.log('1. Erlaubter Empfänger (eigener Chat):');
assertNoThrow(
    'chatId === user_chat_id → erlaubt',
    MY_CHAT_ID, CONFIG_OK
);

// 2. KERN-SAFETY-TEST: fremde Person
console.log('\n2. 🔥 KERN-SAFETY-TEST: Senden an fremde Person (z.B. Marie):');
assertThrows(
    'chatId === Marie → blockiert',
    SARAH_CHAT_ID, CONFIG_OK, 'Safety:'
);
assertThrows(
    'Error-Message nennt die geblockte chatId',
    SARAH_CHAT_ID, CONFIG_OK, SARAH_CHAT_ID
);

// 3. Gruppenchat
console.log('\n3. Senden in Gruppenchat:');
assertThrows(
    'chatId === Gruppe → blockiert',
    GROUP_CHAT_ID, CONFIG_OK, 'Safety:'
);

// 4. Kein user_chat_id konfiguriert
console.log('\n4. user_chat_id nicht konfiguriert (null):');
assertThrows(
    'config.user_chat_id === null → blockiert',
    MY_CHAT_ID, CONFIG_NO_ID, 'Safety:'
);
assertThrows(
    'Auch fremde chatId wenn nicht konfiguriert → blockiert',
    SARAH_CHAT_ID, CONFIG_NO_ID, 'Safety:'
);

// 5. Leere user_chat_id
console.log('\n5. user_chat_id ist leerer String:');
assertThrows(
    'config.user_chat_id === "" → blockiert',
    MY_CHAT_ID, CONFIG_EMPTY, 'Safety:'
);

// 6. Edge case: chatId ist leer
console.log('\n6. Edge case: chatId ist leer oder undefined:');
assertThrows(
    'chatId === "" → blockiert',
    '', CONFIG_OK, 'Safety:'
);
assertThrows(
    'chatId === undefined → blockiert',
    undefined, CONFIG_OK, 'Safety:'
);

// 7. Error-Message enthält "Safety:" Prefix (Voraussetzung für 403-Erkennung im Endpoint)
console.log('\n7. Error-Message Prefix (Voraussetzung für HTTP 403 im Endpoint):');
{
    let errorMessage = null;
    try {
        assertSendAllowed(SARAH_CHAT_ID, CONFIG_OK);
    } catch (err) {
        errorMessage = err.message;
    }
    assert(
        'Error-Message beginnt mit "Safety:" → Endpoint gibt 403 statt 500',
        errorMessage !== null && errorMessage.startsWith('Safety:')
    );
}

// ─── Zusammenfassung ──────────────────────────────────────────────────────────
console.log('\n' + '='.repeat(60));
console.log(`Ergebnis: ${passed} Tests bestanden, ${failed} Tests fehlgeschlagen`);
console.log('='.repeat(60) + '\n');

if (failed > 0) {
    console.error('❌ FEHLER: Send-Guard ist nicht korrekt implementiert!');
    console.error('   Nachrichten könnten an unberechtigte Empfänger gesendet werden.');
    process.exit(1);
} else {
    console.log('✅ ERFOLG: Send-Guard schützt zuverlässig vor unberechtigtem Senden.');
    console.log('🦕 2nd Memory sendet Nachrichten nur an den eigenen Chat.');
}
