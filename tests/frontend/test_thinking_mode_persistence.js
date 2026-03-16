/**
 * test_thinking_mode_persistence.js
 *
 * Akzeptanztests AT-UI-001 bis AT-UI-005:
 * Thinking-Mode-Toggle-Status wird in localStorage gespeichert und beim
 * Laden der Seite wiederhergestellt.
 *
 * Implementierungsdetail: Der tatsaechliche localStorage-Key lautet
 * 'thinkingModeEnabled' (nicht 'memosaur_thinking_mode' -- das war die
 * urspruengliche Spezifikation, die von der Implementierung abweicht).
 *
 * Relevante Stellen im Quellcode:
 *   - Speichern: frontend/index.html Zeile 308 (onchange-Handler des Toggles)
 *   - Wiederherstellen: frontend/index.html Zeile 957-960 (initApp)
 *   - Verwendung: frontend/chat.js Zeile 73 (use_thinking_mode im API-Request)
 *
 * Ausfuehren: node tests/frontend/test_thinking_mode_persistence.js
 */

'use strict';

// ─── Test-Infrastruktur ───────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function assert(description, condition) {
    if (condition) {
        console.log(`  PASS: ${description}`);
        passed++;
    } else {
        console.error(`  FAIL: ${description}`);
        failed++;
    }
}

// ─── Mock localStorage ────────────────────────────────────────────────────────

const localStorageMock = (() => {
    let store = {};
    return {
        getItem: (key) => store[key] ?? null,
        setItem: (key, value) => { store[key] = String(value); },
        clear: () => { store = {}; },
    };
})();

// ─── Extrahierte Produktionslogik ─────────────────────────────────────────────
//
// Die folgenden Funktionen spiegeln exakt die Logik aus index.html wider:
//   - onToggleChange: der onchange-Handler des Checkboxes (Zeile 308)
//   - initThinkingMode: der Restore-Block aus initApp (Zeilen 957-960)
//
// window-State und DOM-Element werden durch einfache Objekte simuliert.

/**
 * Simuliert: onchange="window._thinkingModeEnabled = this.checked;
 *                      localStorage.setItem('thinkingModeEnabled', this.checked)"
 *
 * @param {boolean} checked - Neuer Zustand des Toggle-Checkboxes
 * @param {{ _thinkingModeEnabled: boolean }} win - window-Mock
 * @param {typeof localStorageMock} storage - localStorage-Mock
 */
function onToggleChange(checked, win, storage) {
    win._thinkingModeEnabled = checked;
    storage.setItem('thinkingModeEnabled', checked);
}

/**
 * Simuliert den Restore-Block aus initApp:
 *   const savedThinking = localStorage.getItem('thinkingModeEnabled') === 'true';
 *   window._thinkingModeEnabled = savedThinking;
 *   const toggle = document.getElementById('thinking-mode-toggle');
 *   if (toggle) toggle.checked = savedThinking;
 *
 * @param {{ _thinkingModeEnabled: boolean }} win - window-Mock
 * @param {{ checked: boolean }|null} toggle - DOM-Element-Mock (oder null)
 * @param {typeof localStorageMock} storage - localStorage-Mock
 */
function initThinkingMode(win, toggle, storage) {
    const savedThinking = storage.getItem('thinkingModeEnabled') === 'true';
    win._thinkingModeEnabled = savedThinking;
    if (toggle) toggle.checked = savedThinking;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

console.log('\n=== Thinking Mode Persistence -- Akzeptanztests AT-UI-001 bis AT-UI-005 ===\n');

// AT-UI-001: Toggle ON --> localStorage enthaelt 'true'
console.log('AT-UI-001: Toggle ON --> localStorage enthaelt "true"');
{
    localStorageMock.clear();
    const win = { _thinkingModeEnabled: false };

    onToggleChange(true, win, localStorageMock);

    assert('localStorage["thinkingModeEnabled"] === "true"',
        localStorageMock.getItem('thinkingModeEnabled') === 'true');
    assert('window._thinkingModeEnabled === true',
        win._thinkingModeEnabled === true);
}

// AT-UI-002: Toggle OFF --> localStorage enthaelt 'false'
console.log('\nAT-UI-002: Toggle OFF --> localStorage enthaelt "false"');
{
    localStorageMock.clear();
    const win = { _thinkingModeEnabled: true };

    onToggleChange(false, win, localStorageMock);

    assert('localStorage["thinkingModeEnabled"] === "false"',
        localStorageMock.getItem('thinkingModeEnabled') === 'false');
    assert('window._thinkingModeEnabled === false',
        win._thinkingModeEnabled === false);
}

// AT-UI-003: Init mit localStorage='true' --> Thinking Mode aktiv
console.log('\nAT-UI-003: Init mit gespeichertem Wert "true" --> Thinking Mode ist aktiv');
{
    localStorageMock.clear();
    localStorageMock.setItem('thinkingModeEnabled', 'true');

    const win = { _thinkingModeEnabled: false };
    const toggleEl = { checked: false };

    initThinkingMode(win, toggleEl, localStorageMock);

    assert('window._thinkingModeEnabled === true', win._thinkingModeEnabled === true);
    assert('toggle.checked === true', toggleEl.checked === true);
}

// AT-UI-004: Init mit localStorage='false' --> Thinking Mode inaktiv
console.log('\nAT-UI-004: Init mit gespeichertem Wert "false" --> Thinking Mode ist inaktiv');
{
    localStorageMock.clear();
    localStorageMock.setItem('thinkingModeEnabled', 'false');

    const win = { _thinkingModeEnabled: true };
    const toggleEl = { checked: true };

    initThinkingMode(win, toggleEl, localStorageMock);

    assert('window._thinkingModeEnabled === false', win._thinkingModeEnabled === false);
    assert('toggle.checked === false', toggleEl.checked === false);
}

// AT-UI-005: Init ohne localStorage-Eintrag --> Default ist false (inaktiv)
console.log('\nAT-UI-005: Init ohne localStorage-Eintrag --> Default ist false (inaktiv)');
{
    localStorageMock.clear();
    // Kein setItem -- localStorage ist leer, getItem gibt null zurueck

    const win = { _thinkingModeEnabled: true }; // Ausgangswert egal
    const toggleEl = { checked: true };

    initThinkingMode(win, toggleEl, localStorageMock);

    assert('localStorage gibt null zurueck bei fehlendem Key',
        localStorageMock.getItem('thinkingModeEnabled') === null);
    assert('window._thinkingModeEnabled === false (Default)',
        win._thinkingModeEnabled === false);
    assert('toggle.checked === false (Default)',
        toggleEl.checked === false);
}

// ─── Bonustest: Toggle-Sequenz ON → OFF → ON ──────────────────────────────────
console.log('\nBonus: Toggle-Sequenz ON -> OFF -> ON speichert letzten Zustand korrekt');
{
    localStorageMock.clear();
    const win = { _thinkingModeEnabled: false };

    onToggleChange(true, win, localStorageMock);
    onToggleChange(false, win, localStorageMock);
    onToggleChange(true, win, localStorageMock);

    assert('Nach ON-OFF-ON: localStorage === "true"',
        localStorageMock.getItem('thinkingModeEnabled') === 'true');
    assert('Nach ON-OFF-ON: window._thinkingModeEnabled === true',
        win._thinkingModeEnabled === true);
}

// ─── Bonustest: Init ohne DOM-Toggle-Element (toggle = null) ─────────────────
console.log('\nBonus: initThinkingMode ohne DOM-Element (toggle = null) wirft keinen Fehler');
{
    localStorageMock.clear();
    localStorageMock.setItem('thinkingModeEnabled', 'true');

    const win = { _thinkingModeEnabled: false };
    let threw = false;

    try {
        initThinkingMode(win, null, localStorageMock);
    } catch (e) {
        threw = true;
    }

    assert('Kein Fehler wenn toggle-Element nicht vorhanden', threw === false);
    assert('window._thinkingModeEnabled trotzdem korrekt gesetzt',
        win._thinkingModeEnabled === true);
}

// ─── Zusammenfassung ──────────────────────────────────────────────────────────
console.log('\n' + '='.repeat(60));
console.log(`Ergebnis: ${passed} Tests bestanden, ${failed} Tests fehlgeschlagen`);
console.log('='.repeat(60) + '\n');

if (failed > 0) {
    process.exit(1);
}
