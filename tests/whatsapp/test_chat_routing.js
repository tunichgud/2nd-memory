/**
 * test_chat_routing.js – Regressionstest für Chat-Routing Bug-Fix
 *
 * KONTEXT:
 * ========
 * Bug: 2nd Memory hat in fremde WhatsApp-Chats geantwortet (z.B. an Marie),
 *      wenn der User dort eine eigene Nachricht geschrieben hat.
 *
 * Root Cause: Bei `fromMe: true` gibt WhatsApp `msg.from` als eigene Telefonnummer
 *             zurück — unabhängig vom Chat. Die alte Sicherheitsprüfung hat daher
 *             fälschlicherweise eigene Nachrichten in Fremdchats durchgelassen.
 *
 * Neue Logik (index.js Zeile 153):
 *   Verarbeite nur wenn: fromMe=true UND msg.to === user_chat_id
 *   (= Nachricht die ich an mich selbst geschickt habe)
 *   Bot-Nachrichten (🦕) werden davor bereits herausgefiltert.
 *
 * Ausführung: node tests/whatsapp/test_chat_routing.js
 */

let passed = 0;
let failed = 0;

function assert(description, condition) {
    if (condition) {
        console.log(`  ✅ PASS: ${description}`);
        passed++;
    } else {
        console.error(`  ❌ FAIL: ${description}`);
        failed++;
    }
}

// ─── Extrahierte Routing-Logik aus index.js (Zeile 153) ──────────────────────

/**
 * Prüft ob eine Nachricht verarbeitet werden soll.
 * Exakte Spiegelung der Logik aus index.js:
 *   if (!msg.fromMe || msg.to !== BOT_CONFIG.user_chat_id) { return; }
 *
 * @param {Object} msg - Simulierte WhatsApp-Nachricht
 * @param {string} userChatId - Die konfigurierte User-Chat-ID
 * @returns {boolean} - true = verarbeiten, false = ignorieren
 */
function shouldProcess(msg, userChatId) {
    if (!msg.fromMe || msg.to !== userChatId) {
        return false;
    }
    return true;
}

/**
 * ALTE BUGGY-LOGIK (nur für Regressionsnachweis!)
 * Nutzte msg.from direkt ohne fromMe/to-Berücksichtigung.
 */
function shouldProcessBuggy(msg, userChatId) {
    // BUGGY: Bei fromMe=true ist msg.from immer die eigene ID — matcht daher
    // fälschlicherweise auch Nachrichten in fremden Chats!
    return msg.from === userChatId;
}

// ─── Test-Fixtures ────────────────────────────────────────────────────────────

const USER_CHAT_ID  = '491701234567@c.us';  // User's eigene WhatsApp-ID
const SARAH_CHAT_ID = '491709876543@c.us';  // Maries WhatsApp-ID
const GROUP_CHAT_ID = '123456789@g.us';     // Gruppen-ID

// ─── Tests ────────────────────────────────────────────────────────────────────

console.log('\n=== Chat-Routing Regression Tests ===\n');

// 1. Kern-Use-Case: Ich schreibe mir selbst → Bot antwortet
console.log('1. Ich schreibe mir selbst (eigener Chat):');
{
    const msg = {
        from: USER_CHAT_ID,   // bei fromMe=true immer eigene ID
        to:   USER_CHAT_ID,   // Empfänger = ich selbst
        fromMe: true,
        body: 'Was habe ich letzte Woche mit Max besprochen?'
    };

    assert('fromMe=true + to=eigene ID → verarbeiten', shouldProcess(msg, USER_CHAT_ID) === true);
}

// 2. KERN-REGRESSIONSTEST: Ich schreibe Marie → Bot darf NICHT antworten
console.log('\n2. 🔥 KERN-REGRESSIONSTEST: Ich schreibe an Marie:');
{
    const msg = {
        from: USER_CHAT_ID,   // WhatsApp gibt bei fromMe=true IMMER eigene ID zurück!
        to:   SARAH_CHAT_ID,  // Empfänger = Marie
        fromMe: true,
        body: 'ja'            // Genau die Nachricht aus dem gemeldeten Bug!
    };

    assert('fromMe=true + to=Marie → IGNORIEREN', shouldProcess(msg, USER_CHAT_ID) === false);

    // Nachweis: Alter Code hätte diese Nachricht fälschlich verarbeitet
    assert('🐛 Alte Logik hätte "ja" an Marie fälschlich verarbeitet', shouldProcessBuggy(msg, USER_CHAT_ID) === true);
    assert('✅ Neue Logik verhindert den Bug', shouldProcess(msg, USER_CHAT_ID) === false);
}

// 3. Eingehende Nachricht (von wem auch immer) → ignorieren
console.log('\n3. Eingehende Nachricht von außen (z.B. Marie schreibt mir):');
{
    const msg = {
        from: SARAH_CHAT_ID,
        to:   USER_CHAT_ID,
        fromMe: false,
        body: 'Hast du morgen Zeit?'
    };

    assert('fromMe=false → immer ignorieren', shouldProcess(msg, USER_CHAT_ID) === false);
}

// 4. Ich schreibe in Gruppenchat → ignorieren
console.log('\n4. Ich schreibe in einen Gruppenchat:');
{
    const msg = {
        from: USER_CHAT_ID,
        to:   GROUP_CHAT_ID,
        fromMe: true,
        body: 'Wir treffen uns um 18 Uhr'
    };

    assert('fromMe=true + to=Gruppe → IGNORIEREN', shouldProcess(msg, USER_CHAT_ID) === false);
}

// 5. Edge case: msg.to ist undefined → kein Crash, ignorieren
console.log('\n5. Edge case: msg.to ist undefined:');
{
    const msg = {
        from: USER_CHAT_ID,
        to:   undefined,
        fromMe: true,
        body: 'Edge case'
    };

    assert('to=undefined → kein Crash, ignorieren', shouldProcess(msg, USER_CHAT_ID) === false);
}

// 6. Edge case: msg.to ist null → kein Crash, ignorieren
console.log('\n6. Edge case: msg.to ist null:');
{
    const msg = {
        from: USER_CHAT_ID,
        to:   null,
        fromMe: true,
        body: 'Edge case null'
    };

    assert('to=null → kein Crash, ignorieren', shouldProcess(msg, USER_CHAT_ID) === false);
}

// 7. Szenario-Test: Nachrichtenfolge wie im echten Betrieb
console.log('\n7. Szenario-Test: Gemischte Nachrichtenfolge:');
{
    const messages = [
        // fromMe  | to              | erwartet | beschreibung
        { from: USER_CHAT_ID,  to: USER_CHAT_ID,  fromMe: true,  body: 'An mich' },       // ✅
        { from: USER_CHAT_ID,  to: SARAH_CHAT_ID, fromMe: true,  body: 'An Marie' },      // ❌ Bug-Case
        { from: SARAH_CHAT_ID, to: USER_CHAT_ID,  fromMe: false, body: 'Von Marie' },     // ❌
        { from: USER_CHAT_ID,  to: GROUP_CHAT_ID, fromMe: true,  body: 'An Gruppe' },     // ❌
        { from: USER_CHAT_ID,  to: USER_CHAT_ID,  fromMe: true,  body: 'Noch eine' },     // ✅
    ];
    const expected = [true, false, false, false, true];
    const results  = messages.map(m => shouldProcess(m, USER_CHAT_ID));

    let allCorrect = true;
    for (let i = 0; i < messages.length; i++) {
        if (results[i] !== expected[i]) {
            allCorrect = false;
            console.error(`    Nachricht ${i+1} ("${messages[i].body}"): erwartet=${expected[i]}, got=${results[i]}`);
        }
    }
    assert('Alle 5 Nachrichten korrekt klassifiziert', allCorrect);
}

// ─── Zusammenfassung ──────────────────────────────────────────────────────────
console.log('\n' + '='.repeat(60));
console.log(`Ergebnis: ${passed} Tests bestanden, ${failed} Tests fehlgeschlagen`);
console.log('='.repeat(60) + '\n');

if (failed > 0) {
    console.error('❌ FEHLER: Einige Tests sind fehlgeschlagen!');
    process.exit(1);
} else {
    console.log('✅ ERFOLG: Alle Tests bestanden!');
    console.log('🦕 2nd Memory antwortet nur noch auf Nachrichten von mir an mich selbst.');
}
