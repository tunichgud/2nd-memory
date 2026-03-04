/**
 * sync.js – Web Crypto API Verschlüsselung + Server-Sync für memosaur v2.
 *
 * Das Passwort verlässt NIEMALS den Browser.
 * Auf dem Server liegt nur ein AES-GCM verschlüsselter Blob.
 *
 * Ablauf Export:
 *   1. Wörterbuch aus IndexedDB lesen
 *   2. JSON serialisieren
 *   3. PBKDF2: Passwort → AES-256-GCM Key
 *   4. AES-GCM verschlüsseln (random IV)
 *   5. Blob + IV als Base64 an Server schicken
 *
 * Ablauf Import:
 *   1. Blob + IV vom Server holen
 *   2. PBKDF2: Passwort → Key (gleiche Salt wie beim Export)
 *   3. AES-GCM entschlüsseln
 *   4. JSON → Wörterbuch → IndexedDB
 */

const PBKDF2_ITERATIONS = 250_000;
const PBKDF2_HASH       = 'SHA-256';
const AES_KEY_LENGTH    = 256;

// Salt ist fix pro Anwendung (kein Geheimnis, nur Domänen-Trennung)
// In einer Multi-Tenant-Umgebung sollte der Salt user-spezifisch sein.
const APP_SALT = new TextEncoder().encode('memosaur-v2-salt-2025');

// ---------------------------------------------------------------------------
// Schlüsselableitung
// ---------------------------------------------------------------------------

async function _deriveKey(password) {
  const enc      = new TextEncoder();
  const keyMat   = await crypto.subtle.importKey(
    'raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: APP_SALT, iterations: PBKDF2_ITERATIONS, hash: PBKDF2_HASH },
    keyMat,
    { name: 'AES-GCM', length: AES_KEY_LENGTH },
    false,
    ['encrypt', 'decrypt'],
  );
}

// ---------------------------------------------------------------------------
// Verschlüsselung / Entschlüsselung
// ---------------------------------------------------------------------------

async function encryptData(plaintext, password) {
  const key = await _deriveKey(password);
  const iv  = crypto.getRandomValues(new Uint8Array(12));
  const enc = new TextEncoder();
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    enc.encode(plaintext),
  );
  return {
    blob: _bufToBase64(ciphertext),
    iv:   _bufToBase64(iv.buffer),
  };
}

async function decryptData(blobB64, ivB64, password) {
  const key       = await _deriveKey(password);
  const cipherBuf = _base64ToBuf(blobB64);
  const iv        = new Uint8Array(_base64ToBuf(ivB64));
  const plainBuf  = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipherBuf);
  return new TextDecoder().decode(plainBuf);
}

// ---------------------------------------------------------------------------
// Export / Import des Token-Wörterbuchs
// ---------------------------------------------------------------------------

/**
 * Verschlüsselt das komplette Wörterbuch und lädt es zum Server hoch.
 * @param {string} userId
 * @param {string} password
 * @param {string} deviceHint – Optional, z.B. "Firefox/Linux"
 */
async function exportAndSync(userId, password, deviceHint) {
  const tokens  = await window.TokenStore.getAllTokens();
  const json    = JSON.stringify(tokens);
  const { blob, iv } = await encryptData(json, password);

  const res = await fetch(`/api/v1/sync/${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ blob, iv, device_hint: deviceHint || navigator.userAgent.slice(0, 50) }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(`Sync-Upload fehlgeschlagen: ${err.detail}`);
  }

  const data = await res.json();
  console.log('[Sync] Upload erfolgreich, Version:', data.version);
  return data;
}

/**
 * Lädt den neuesten Blob vom Server und entschlüsselt das Wörterbuch.
 * Importiert die Einträge in die lokale IndexedDB.
 * @param {string} userId
 * @param {string} password
 */
async function importFromSync(userId, password) {
  const res = await fetch(`/api/v1/sync/${encodeURIComponent(userId)}`);
  if (res.status === 404) throw new Error('Kein Sync-Blob auf dem Server vorhanden.');
  if (!res.ok) throw new Error(`Sync-Download fehlgeschlagen: ${res.statusText}`);

  const { blob, iv, version } = await res.json();
  const json    = await decryptData(blob, iv, password);
  const entries = JSON.parse(json);
  const count   = await window.TokenStore.importTokens(entries);
  console.log('[Sync] Import erfolgreich:', count, 'Einträge, Version:', version);
  return { count, version };
}

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

function _bufToBase64(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}

function _base64ToBuf(b64) {
  const bin  = atob(b64);
  const buf  = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}

// ---------------------------------------------------------------------------
// Sync-UI
// ---------------------------------------------------------------------------

function renderSyncUI(containerId, userId) {
  const el = document.getElementById(containerId);
  if (!el) return;

  el.innerHTML = `
    <div class="flex flex-col gap-3 text-sm">
      <p class="text-gray-400 text-xs">
        Das Token-Wörterbuch (Name↔Token Zuordnung) wird verschlüsselt auf dem Server gespeichert.
        Das Passwort verlässt deinen Browser nicht.
      </p>
      <div class="flex gap-2 items-center">
        <input id="sync-password" type="password" placeholder="Sync-Passwort"
          class="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
      </div>
      <div class="flex gap-2">
        <button onclick="syncExport('${userId}')"
          class="flex-1 bg-blue-700 hover:bg-blue-600 rounded px-3 py-2 text-sm font-medium">
          Hochladen (Export)
        </button>
        <button onclick="syncImport('${userId}')"
          class="flex-1 bg-gray-700 hover:bg-gray-600 rounded px-3 py-2 text-sm font-medium">
          Wiederherstellen (Import)
        </button>
      </div>
      <div id="sync-result" class="text-xs"></div>
    </div>
  `;
}

async function syncExport(userId) {
  const pw  = document.getElementById('sync-password')?.value;
  const res = document.getElementById('sync-result');
  if (!pw) { if (res) res.innerHTML = '<span class="text-red-400">Passwort eingeben.</span>'; return; }
  if (res) res.innerHTML = '<span class="text-gray-400">Verschlüssle und lade hoch…</span>';
  try {
    const data = await exportAndSync(userId, pw);
    if (res) res.innerHTML = `<span class="text-green-400">Gespeichert (Version ${data.version}).</span>`;
  } catch (e) {
    if (res) res.innerHTML = `<span class="text-red-400">${e.message}</span>`;
  }
}

async function syncImport(userId) {
  const pw  = document.getElementById('sync-password')?.value;
  const res = document.getElementById('sync-result');
  if (!pw) { if (res) res.innerHTML = '<span class="text-red-400">Passwort eingeben.</span>'; return; }
  if (res) res.innerHTML = '<span class="text-gray-400">Lade herunter und entschlüssle…</span>';
  try {
    const data = await importFromSync(userId, pw);
    if (res) res.innerHTML = `<span class="text-green-400">${data.count} Einträge wiederhergestellt (v${data.version}).</span>`;
  } catch (e) {
    if (res) res.innerHTML = `<span class="text-red-400">${e.message}</span>`;
  }
}

window.Sync = { exportAndSync, importFromSync, renderSyncUI };
window.syncExport  = syncExport;
window.syncImport  = syncImport;
