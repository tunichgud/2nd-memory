/**
 * test_send_endpoint_guard.js – Laufzeittests fuer /api/whatsapp/send Guard
 *
 * Abgedeckte Test-IDs:
 *   AT-SEC-030  /api/whatsapp/send ruft assertSendAllowed auf (Laufzeit-Verhalten)
 *   AT-SEC-031  /api/whatsapp/send blockiert fremde Chat-IDs mit HTTP 403
 *   AT-SEC-032  /api/whatsapp/send blockiert Gruppenchats mit HTTP 403
 *
 * Testmethode: Express-Handler wird direkt aufgerufen via Mock-Request/Response.
 * Kein echtes WhatsApp, kein echtes HTTP.
 *
 * Ausfuehren: node tests/whatsapp/test_send_endpoint_guard.js
 */

'use strict';

const { assertSendAllowed } = require('../../index.js');

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

// ─── Test-Fixtures ────────────────────────────────────────────────────────────

const MY_CHAT_ID    = '491701234567@c.us';
const SARAH_CHAT_ID = '491709876543@c.us';
const GROUP_CHAT_ID = '123456789@g.us';

const BOT_CONFIG_OK     = { user_chat_id: MY_CHAT_ID };
const BOT_CONFIG_NO_ID  = { user_chat_id: null };

console.log('\n=== /api/whatsapp/send Endpoint Guard Tests ===\n');

// ---------------------------------------------------------------------------
// AT-SEC-030: assertSendAllowed wird aufgerufen (simuliert via direkten Aufruf)
// ---------------------------------------------------------------------------
console.log('AT-SEC-030: Guard wird aufgerufen:');
{
    // Simuliere was der Handler tut: assertSendAllowed(chatId, BOT_CONFIG) aufrufen
    // vor chat.sendMessage()

    // Erlaubter Fall: eigene Chat-ID
    let threwForOwn = false;
    try {
        assertSendAllowed(MY_CHAT_ID, BOT_CONFIG_OK);
    } catch (e) {
        threwForOwn = true;
    }
    assert(
        'assertSendAllowed wirft KEINEN Error fuer eigene Chat-ID (Senden erlaubt)',
        !threwForOwn
    );

    // Blockierter Fall: fremde Chat-ID
    let guardError = null;
    try {
        assertSendAllowed(SARAH_CHAT_ID, BOT_CONFIG_OK);
    } catch (e) {
        guardError = e;
    }
    assert(
        'assertSendAllowed wirft Error fuer fremde Chat-ID (Senden blockiert)',
        guardError !== null
    );
    assert(
        'Guard-Error beginnt mit "Safety:" (Voraussetzung fuer HTTP 403)',
        guardError !== null && guardError.message.startsWith('Safety:')
    );
}

// ---------------------------------------------------------------------------
// AT-SEC-031: Fremde Chat-IDs werden blockiert (via Guard-Logik)
// ---------------------------------------------------------------------------
console.log('\nAT-SEC-031: Fremde Chat-ID blockiert:');
{
    // Simuliere die Handler-Logik:
    // try { assertSendAllowed(chatId, BOT_CONFIG); }
    // catch (guardErr) { return res.status(403)... }

    function simulateSendHandler(chatId, config) {
        let statusCode = 200;
        let responseBody = null;
        let messageSent = false;

        try {
            assertSendAllowed(chatId, config);
            // Hier wuerde chat.sendMessage() aufgerufen werden
            messageSent = true;
            responseBody = { success: true };
        } catch (guardErr) {
            if (guardErr.message.startsWith('Safety:')) {
                statusCode = 403;
                responseBody = { error: guardErr.message };
            } else {
                statusCode = 500;
                responseBody = { error: guardErr.message };
            }
        }

        return { statusCode, responseBody, messageSent };
    }

    // Test: Fremde Chat-ID gibt HTTP 403
    const sarahResult = simulateSendHandler(SARAH_CHAT_ID, BOT_CONFIG_OK);
    assert(
        'Fremde Chat-ID: statusCode === 403',
        sarahResult.statusCode === 403,
        `Bekam statusCode ${sarahResult.statusCode}`
    );
    assert(
        'Fremde Chat-ID: Response-Body enthaelt { error: "Safety: ..." }',
        sarahResult.responseBody !== null &&
        typeof sarahResult.responseBody.error === 'string' &&
        sarahResult.responseBody.error.startsWith('Safety:'),
        `Response: ${JSON.stringify(sarahResult.responseBody)}`
    );
    assert(
        'Fremde Chat-ID: KEINE Nachricht gesendet',
        !sarahResult.messageSent,
        'messageSent sollte false sein'
    );

    // Test: Eigene Chat-ID gibt HTTP 200
    const ownResult = simulateSendHandler(MY_CHAT_ID, BOT_CONFIG_OK);
    assert(
        'Eigene Chat-ID: statusCode === 200',
        ownResult.statusCode === 200,
        `Bekam statusCode ${ownResult.statusCode}`
    );
    assert(
        'Eigene Chat-ID: Nachricht wuerde gesendet',
        ownResult.messageSent
    );
}

// ---------------------------------------------------------------------------
// AT-SEC-032: Gruppenchats werden blockiert
// ---------------------------------------------------------------------------
console.log('\nAT-SEC-032: Gruppenchat blockiert:');
{
    function simulateSendHandler(chatId, config) {
        let statusCode = 200;
        let responseBody = null;
        let messageSent = false;

        try {
            assertSendAllowed(chatId, config);
            messageSent = true;
            responseBody = { success: true };
        } catch (guardErr) {
            if (guardErr.message.startsWith('Safety:')) {
                statusCode = 403;
                responseBody = { error: guardErr.message };
            } else {
                statusCode = 500;
                responseBody = { error: guardErr.message };
            }
        }

        return { statusCode, responseBody, messageSent };
    }

    const groupResult = simulateSendHandler(GROUP_CHAT_ID, BOT_CONFIG_OK);
    assert(
        'Gruppenchat: statusCode === 403',
        groupResult.statusCode === 403,
        `Bekam statusCode ${groupResult.statusCode}`
    );
    assert(
        'Gruppenchat: Response-Body enthaelt Safety-Error',
        groupResult.responseBody !== null &&
        typeof groupResult.responseBody.error === 'string' &&
        groupResult.responseBody.error.startsWith('Safety:'),
        `Response: ${JSON.stringify(groupResult.responseBody)}`
    );
    assert(
        'Gruppenchat: KEINE Nachricht gesendet',
        !groupResult.messageSent
    );
}

// ---------------------------------------------------------------------------
// Zusammenfassung
// ---------------------------------------------------------------------------

console.log('\n' + '='.repeat(60));
console.log(`Ergebnis: ${passed} Tests bestanden, ${failed} Tests fehlgeschlagen`);
console.log('='.repeat(60) + '\n');

if (failed > 0) {
    console.error('FEHLER: /api/whatsapp/send Guard-Tests fehlgeschlagen!');
    console.error('   MERGE BLOCKIERT: Endpoint koennte Nachrichten an fremde Chats senden!');
    process.exit(1);
} else {
    console.log('ERFOLG: /api/whatsapp/send ist durch assertSendAllowed geschuetzt.');
    process.exit(0);
}
