/**
 * test_ner_masking.js – Unit-Tests für die NER Maskierungs-Logik
 *
 * Testet speziell den Bug bei dem `start: null` durch eine `!== undefined` Prüfung
 * fiel und dann `text.slice(0, null)` einen leeren String produzierte.
 *
 * Ausführung: node tests/frontend/test_ner_masking.js
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

// ─── Reproduzierte isolierte Kern-Logik aus ner.js ───────────────────────────

/**
 * Simuliert das Token-Zuweisen und Text-Ersetzen aus maskText().
 * Dies ist der kritische Abschnitt in dem der Bug aufgetreten ist.
 */
function applyMaskingLogic(text, entities, tokenMap) {
    // Sortierung rückwärts (wie im Original)
    const sorted = [...entities].sort((a, b) => (b.start || 0) - (a.start || 0));

    let masked = text;
    const assigned = [];

    for (const ent of sorted) {
        const token = tokenMap[ent.word] || `[TOK]`;
        assigned.push({ word: ent.word, token, type: ent.entity_group });

        // GEREPARIERTER NULL-GUARD: != null fängt sowohl null als auch undefined
        if (ent.start != null && ent.end != null) {
            masked = masked.slice(0, ent.start) + token + masked.slice(ent.end);
        } else {
            masked = masked.replace(ent.word, token);
        }
    }

    return { masked, assigned };
}

/**
 * Gleiche Logik aber MIT dem alten Bug (`!== undefined`).
 * Dient zum Nachweisen dass der Bug auch wirklich existiert hatte.
 */
function applyMaskingLogicBuggy(text, entities, tokenMap) {
    const sorted = [...entities].sort((a, b) => (b.start || 0) - (a.start || 0));
    let masked = text;

    for (const ent of sorted) {
        const token = tokenMap[ent.word] || `[TOK]`;
        // BUGGY: null !== undefined ist true! Führt zu slice(0, null) = ""
        if (ent.start !== undefined && ent.end !== undefined) {
            masked = masked.slice(0, ent.start) + token + masked.slice(ent.end);
        } else {
            masked = masked.replace(ent.word, token);
        }
    }
    return masked;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

console.log('\n=== NER Null-Guard Regression Tests ===\n');

// 1. Haupttest: start/end = null (wie Transformers.js ohne Aggregation liefert)
console.log('1. Masking mit null start/end (Transformers.js ohne Aggregation):');
{
    const text = 'Wie hat sich Sarah gefühlt, als ich mit Nora in München war?';
    const entities = [
        { entity: 'B-PER', score: 0.9996, index: 4, word: 'Sarah', start: null, end: null, entity_group: 'PER' },
        { entity: 'B-PER', score: 0.9993, index: 16, word: 'Nora', start: null, end: null, entity_group: 'PER' },
        { entity: 'B-LOC', score: 0.9997, index: 18, word: 'München', start: null, end: null, entity_group: 'LOC' },
    ];
    const tokenMap = { 'Sarah': '[PER_1]', 'Nora': '[PER_2]', 'München': '[LOC_1]' };

    const { masked, assigned } = applyMaskingLogic(text, entities, tokenMap);

    assert('Text ist nicht leer', masked.length > 0);
    assert('Text enthält keinen Klarnamen "Sarah"', !masked.includes('Sarah'));
    assert('Text enthält keinen Klarnamen "Nora"', !masked.includes('Nora'));
    assert('Text enthält keinen Klarnamen "München"', !masked.includes('München'));
    assert('Text enthält Token [PER_1]', masked.includes('[PER_1]'));
    assert('Text enthält Token [PER_2]', masked.includes('[PER_2]'));
    assert('Text enthält Token [LOC_1]', masked.includes('[LOC_1]'));
    assert('3 Entities wurden korrekt zugeordnet', assigned.length === 3);
}

// 2. Test dass der alte Bug wirklich kaputt war
console.log('\n2. Nachweis dass alter Bug (!== undefined) falsch war:');
{
    const text = 'Hallo Sarah';
    const entity = { word: 'Sarah', start: null, end: null, entity_group: 'PER' };
    const tokenMap = { 'Sarah': '[PER_1]' };

    const buggyResult = applyMaskingLogicBuggy(text, [entity], tokenMap);
    const fixedResult = applyMaskingLogic(text, [entity], tokenMap).masked;

    // Im alten Code: slice(0, null) = "" und slice(null) = ganzer Text
    // → Ergebnis: "" + "[PER_1]" + "Hallo Sarah" = "[PER_1]Hallo Sarah" (Dopplung!)
    // → ODER slice falsch aufgeteilt
    assert('Reparierter Code maskiert korrekt', fixedResult === 'Hallo [PER_1]');
    assert('Alter buggy Code produzierte falschen Output', buggyResult !== 'Hallo [PER_1]');
    assert('Reparierter Code und buggy Code unterscheiden sich', fixedResult !== buggyResult);
}

// 3. Sicherheitstest: start/end als korrekte number-Offsets
console.log('\n3. Masking mit gültigen start/end Offsets (aggregation_strategy=simple):');
{
    const text = 'Sarah lebt in Berlin';
    const entities = [
        { word: 'Sarah', start: 0, end: 5, entity_group: 'PER' },
        { word: 'Berlin', start: 14, end: 20, entity_group: 'LOC' },
    ];
    const tokenMap = { 'Sarah': '[PER_1]', 'Berlin': '[LOC_1]' };

    const { masked } = applyMaskingLogic(text, entities, tokenMap);

    assert('Text enthält kein "Sarah"', !masked.includes('Sarah'));
    assert('Text enthält kein "Berlin"', !masked.includes('Berlin'));
    assert('Text enthält [PER_1]', masked.includes('[PER_1]'));
    assert('Text enthält [LOC_1]', masked.includes('[LOC_1]'));
}

// 4. Edge case: start = 0 (falsy!) muss korrekt behandelt werden
console.log('\n4. Edge case: start = 0 (ist falsy, muss trotzdem als gültig gelten):');
{
    const text = 'Nora ist da';
    const entities = [
        { word: 'Nora', start: 0, end: 4, entity_group: 'PER' },
    ];
    const tokenMap = { 'Nora': '[PER_1]' };

    const { masked } = applyMaskingLogic(text, entities, tokenMap);

    assert('Text enthält kein "Nora"', !masked.includes('Nora'));
    assert('Text beginnt mit [PER_1]', masked.startsWith('[PER_1]'));
}

// ─── Zusammenfassung ──────────────────────────────────────────────────────────
console.log('\n' + '='.repeat(47));
console.log(`Ergebnis: ${passed} Tests bestanden, ${failed} Tests fehlgeschlagen`);
console.log('='.repeat(47) + '\n');

if (failed > 0) {
    process.exit(1);
}
