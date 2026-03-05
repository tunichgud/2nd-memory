/**
 * ner.js – Client-seitige Named Entity Recognition via Transformers.js
 *
 * Modell: Davlan/bert-base-multilingual-cased-ner-hrl (~90 MB ONNX)
 * Läuft vollständig im Browser via WebAssembly. Keine Daten verlassen den Browser.
 *
 * Erkannte Entitätstypen:
 *   PER  → Personennamen
 *   LOC  → Ortsnamen / Locations
 *   ORG  → Organisationen
 *
 * Zustand:
 *   'loading'  – Modell wird geladen
 *   'ready'    – bereit für Maskierung
 *   'error'    – Ladefehler
 */

// Transformers.js via CDN (ESM Build)
import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2/dist/transformers.min.js';

// Konfiguration für Browser-Umgebung
env.allowLocalModels = false;
env.useBrowserCache = true;

const MODEL_ID = 'Xenova/bert-base-multilingual-cased-ner-hrl';

let _pipe = null;
let _state = 'loading';
let _onReady = null;

async function loadNER(onProgress) {
  console.log('[NER] Initialisiere Modell-Download...');
  try {
    _state = 'loading';
    _updateLoadingUI('Initialisiere NER-Modell…');

    _pipe = await pipeline('token-classification', MODEL_ID, {
      aggregation_strategy: 'simple',
      progress_callback: (info) => {
        if (info.status === 'progress') {
          const pct = Math.round(info.progress || 0);
          const file = info.file || '';
          if (onProgress) onProgress(pct, file);
          _updateLoadingUI(`NER-Modell: ${pct}% (${file})`);
        } else if (info.status === 'done') {
          _updateLoadingUI(`NER-Modell: Datei fertig geladen.`);
        } else if (info.status === 'initiate') {
          _updateLoadingUI(`Starte Download: ${info.file || ''}...`);
        }
      },
    });

    _state = 'ready';
    console.log('[NER] Modell vollständig geladen und bereit.');
    _updateLoadingUI(null);
    if (_onReady) _onReady();
  } catch (err) {
    _state = 'error';
    _updateLoadingUI(`NER-Ladefehler: ${err.message}`, true);
    console.error('[NER] Kritischer Ladefehler:', err);
    throw err;
  }
}

/** Setzt einen Callback der aufgerufen wird sobald das Modell bereit ist. */
function onNERReady(cb) {
  if (_state === 'ready') { cb(); return; }
  _onReady = cb;
}

/**
 * Erkennt Entitäten in einem Text.
 * @param {string} text
 * @returns {Promise<Array<{word: string, entity_group: string, score: number}>>}
 */
async function recognizeEntities(text) {
  if (_state !== 'ready' || !_pipe) {
    throw new Error('NER-Modell noch nicht bereit. Bitte warten.');
  }
  if (!text || !text.trim()) return [];

  const results = await _pipe(text);
  // Nur PER, LOC, ORG – MISC ignorieren
  return results.filter(r => ['PER', 'LOC', 'ORG'].includes(r.entity_group));
}

/**
 * Maskiert einen Text: Ersetzt Entitäten durch Tokens aus dem TokenStore.
 *
 * @param {string} text  – Eingabetext (Klartext)
 * @returns {Promise<{masked: string, entities: Array}>}
 *   masked   – Text mit ersetzten Tokens
 *   entities – Liste der gefundenen Entitäten mit zugewiesenen Tokens
 */
async function maskText(text) {
  if (!text || !text.trim()) return { masked: text, entities: [] };

  const entities = await recognizeEntities(text);
  if (!entities.length) return { masked: text, entities: [] };

  // Entitäten nach Position sortieren (wichtig für korrektes Ersetzen)
  // Transformers.js mit aggregation_strategy='simple' gibt start/end zurück
  const sorted = [...entities].sort((a, b) => (b.start || 0) - (a.start || 0));

  let masked = text;
  const assigned = [];

  for (const ent of sorted) {
    const token = await window.TokenStore.getOrCreateToken(ent.word, ent.entity_group);
    assigned.push({ word: ent.word, token, type: ent.entity_group, score: ent.score });

    // Ersetzen via String-Suche (robuster als Offset bei Unicode)
    if (ent.start !== undefined && ent.end !== undefined) {
      masked = masked.slice(0, ent.start) + token + masked.slice(ent.end);
    } else {
      // Fallback: ersten Treffer ersetzen
      masked = masked.replace(ent.word, token);
    }
  }

  return { masked, entities: assigned };
}

/**
 * Maskiert Text und gibt nur den maskierten String zurück.
 * Convenience-Wrapper für einfache Anwendungsfälle.
 */
async function maskTextSimple(text) {
  const { masked } = await maskText(text);
  return masked;
}

// ---- UI-Hilfsfunktion --------------------------------------------------------

function _updateLoadingUI(message, isError = false) {
  const el = document.getElementById('ner-status');
  if (!el) return;
  if (!message) {
    el.classList.add('hidden');
    return;
  }
  el.classList.remove('hidden');
  el.className = `text-xs px-3 py-1 rounded-full ${isError ? 'bg-red-900 text-red-300' : 'bg-yellow-900 text-yellow-200'
    }`;
  el.textContent = message;
}

function getNERState() {
  return _state;
}

// Exportieren
window.NER = {
  loadNER,
  onNERReady,
  getNERState,
  recognizeEntities,
  maskText,
  maskTextSimple,
};
