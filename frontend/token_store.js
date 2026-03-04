/**
 * token_store.js – IndexedDB Token↔Klarname Wörterbuch für memosaur v2.
 *
 * Speichert das Mapping lokal im Browser. Kein Klarname verlässt den Browser
 * ohne explizite Nutzeraktion (Sync-Upload).
 *
 * Token-Format:
 *   PER_1, PER_2, ... → Personennamen
 *   LOC_1, LOC_2, ... → Ortsnamen / Locations
 *   ORG_1, ORG_2, ... → Organisationen
 */

const DB_NAME    = 'memosaur_tokens';
const DB_VERSION = 1;
const STORE_NAME = 'dictionary';

let _db = null;

/** Öffnet (oder erstellt) die IndexedDB. */
async function openTokenDB() {
  if (_db) return _db;
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'token_id' });
        store.createIndex('cleartext_lc', 'cleartext_lc', { unique: false });
        store.createIndex('type',         'type',         { unique: false });
      }
    };
    req.onsuccess  = (e) => { _db = e.target.result; resolve(_db); };
    req.onerror    = (e) => reject(e.target.error);
  });
}

/** Gibt den Typ-Präfix für eine NER-Entitäts-Kategorie zurück. */
function _typePrefix(nerType) {
  if (nerType === 'PER')  return 'PER';
  if (nerType === 'LOC')  return 'LOC';
  if (nerType === 'ORG')  return 'ORG';
  return 'UNK';
}

/**
 * Gibt das Token für einen Klarnamen zurück.
 * Legt einen neuen Eintrag an falls noch nicht vorhanden.
 *
 * @param {string} cleartext  – z.B. "Nora"
 * @param {string} nerType    – "PER" | "LOC" | "ORG"
 * @returns {Promise<string>} – z.B. "[PER_1]"
 */
async function getOrCreateToken(cleartext, nerType) {
  const db = await openTokenDB();
  const lc = cleartext.toLowerCase().trim();
  const prefix = _typePrefix(nerType);

  // Schon vorhanden?
  const existing = await new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE_NAME, 'readonly');
    const idx = tx.objectStore(STORE_NAME).index('cleartext_lc');
    const req = idx.getAll(lc);
    req.onsuccess = (e) => resolve(e.target.result.find(r => r.type === prefix) || null);
    req.onerror   = (e) => reject(e.target.error);
  });
  if (existing) {
    // Zähler erhöhen
    await new Promise((resolve, reject) => {
      const tx    = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      existing.count++;
      const req = store.put(existing);
      req.onsuccess = () => resolve();
      req.onerror   = (e) => reject(e.target.error);
    });
    return `[${existing.token_id}]`;
  }

  // Nächste freie ID für diesen Typ ermitteln
  const all = await getAllTokens();
  const maxN = all
    .filter(e => e.type === prefix)
    .reduce((m, e) => {
      const n = parseInt(e.token_id.split('_')[1], 10);
      return isNaN(n) ? m : Math.max(m, n);
    }, 0);
  const newId = `${prefix}_${maxN + 1}`;

  await new Promise((resolve, reject) => {
    const tx    = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const req   = store.add({
      token_id:    newId,
      cleartext,
      cleartext_lc: lc,
      type:        prefix,
      first_seen:  new Date().toISOString(),
      count:       1,
    });
    req.onsuccess = () => resolve();
    req.onerror   = (e) => reject(e.target.error);
  });

  return `[${newId}]`;
}

/**
 * Gibt den Klarnamen für ein Token zurück, oder das Token selbst falls unbekannt.
 * @param {string} token – z.B. "[PER_1]" oder "PER_1"
 * @returns {Promise<string>}
 */
async function lookupToken(token) {
  const db  = await openTokenDB();
  const key = token.replace(/[\[\]]/g, '');
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).get(key);
    req.onsuccess = (e) => resolve(e.target.result ? e.target.result.cleartext : token);
    req.onerror   = (e) => reject(e.target.error);
  });
}

/**
 * Ersetzt alle Token-Platzhalter in einem Text durch Klarnamen.
 * @param {string} text
 * @returns {Promise<string>}
 */
async function unmaskText(text) {
  const tokens = [...new Set((text.match(/\[(PER|LOC|ORG)_\d+\]/g) || []))];
  let result = text;
  for (const tok of tokens) {
    const cleartext = await lookupToken(tok);
    result = result.replaceAll(tok, cleartext);
  }
  return result;
}

/**
 * Gibt alle gespeicherten Einträge zurück (für Export/Sync).
 * @returns {Promise<Array>}
 */
async function getAllTokens() {
  const db = await openTokenDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).getAll();
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

/**
 * Importiert ein Wörterbuch (z.B. nach Migration oder Sync-Restore).
 * Bestehende Einträge werden nicht überschrieben.
 * @param {Array} entries
 */
async function importTokens(entries) {
  const db = await openTokenDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  const store = tx.objectStore(STORE_NAME);
  for (const entry of entries) {
    await new Promise((res, rej) => {
      const req = store.put(entry);
      req.onsuccess = () => res();
      req.onerror   = () => res(); // Konflikt ignorieren
    });
  }
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve(entries.length);
    tx.onerror    = (e) => reject(e.target.error);
  });
}

/** Löscht das gesamte Wörterbuch (z.B. bei User-Wechsel). */
async function clearTokens() {
  const db = await openTokenDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE_NAME, 'readwrite');
    const req = tx.objectStore(STORE_NAME).clear();
    req.onsuccess = () => resolve();
    req.onerror   = (e) => reject(e.target.error);
  });
}

// Exportieren für andere Module
window.TokenStore = {
  getOrCreateToken,
  lookupToken,
  unmaskText,
  getAllTokens,
  importTokens,
  clearTokens,
};
