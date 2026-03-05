/**
 * sync.js – Web Crypto API Verschlüsselung + automatischer Server-Sync für memosaur v2.
 *
 * Das Passwort verlässt NIEMALS den Browser.
 * Auf dem Server liegt nur ein AES-GCM verschlüsselter Blob.
 *
 * Auto-Sync-Verhalten:
 *   - Beim App-Start: autoDownload() lädt das Wörterbuch vom Server herunter (Merge)
 *   - Nach jeder neuen Token-Vergabe: scheduleUpload() debounced (2s) den Upload
 *   - Passwort wird in localStorage gespeichert (memosaur_sync_pw)
 */

const PBKDF2_ITERATIONS = 250_000;
const PBKDF2_HASH = 'SHA-256';
const AES_KEY_LENGTH = 256;
const SYNC_PW_KEY = 'memosaur_sync_pw';

// Salt ist fix pro Anwendung (kein Geheimnis, nur Domänen-Trennung)
const APP_SALT = new TextEncoder().encode('memosaur-v2-salt-2025');

// Debounce-Timer für Upload
let _uploadTimer = null;

// ---------------------------------------------------------------------------
// Schlüsselableitung
// ---------------------------------------------------------------------------

async function _deriveKey(password) {
  const enc = new TextEncoder();
  const keyMat = await crypto.subtle.importKey(
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
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = new TextEncoder();
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    enc.encode(plaintext),
  );
  return {
    blob: _bufToBase64(ciphertext),
    iv: _bufToBase64(iv.buffer),
  };
}

async function decryptData(blobB64, ivB64, password) {
  const key = await _deriveKey(password);
  const cipherBuf = _base64ToBuf(blobB64);
  const iv = new Uint8Array(_base64ToBuf(ivB64));
  const plainBuf = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipherBuf);
  return new TextDecoder().decode(plainBuf);
}

// ---------------------------------------------------------------------------
// Passwort-Verwaltung (localStorage)
// ---------------------------------------------------------------------------

/** Gibt das gespeicherte Passwort zurück, oder null falls keins gesetzt. */
function getSyncPassword() {
  return localStorage.getItem(SYNC_PW_KEY);
}

/** Speichert das Passwort in localStorage. */
function setSyncPassword(pw) {
  localStorage.setItem(SYNC_PW_KEY, pw);
}

/** Löscht das gespeicherte Passwort. */
function clearSyncPassword() {
  localStorage.removeItem(SYNC_PW_KEY);
}

/** Prüft ob ein Passwort gesetzt ist. */
function hasSyncPassword() {
  const pw = getSyncPassword();
  return pw !== null && pw.length > 0;
}

// ---------------------------------------------------------------------------
// Export / Import des Token-Wörterbuchs (manuell)
// ---------------------------------------------------------------------------

/**
 * Verschlüsselt das komplette Wörterbuch und lädt es zum Server hoch.
 * @param {string} userId
 * @param {string} password
 * @param {string} [deviceHint]
 */
async function exportAndSync(userId, password, deviceHint) {
  const tokens = await window.TokenStore.getAllTokens();
  const json = JSON.stringify(tokens);
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
 * Importiert die Einträge in die lokale IndexedDB (Merge, keine Überschreibung).
 * @param {string} userId
 * @param {string} password
 */
async function importFromSync(userId, password) {
  const res = await fetch(`/api/v1/sync/${encodeURIComponent(userId)}`);
  if (res.status === 404) throw new Error('Kein Sync-Blob auf dem Server vorhanden.');
  if (!res.ok) throw new Error(`Sync-Download fehlgeschlagen: ${res.statusText}`);

  const { blob, iv, version } = await res.json();
  const json = await decryptData(blob, iv, password);
  const entries = JSON.parse(json);
  const count = await window.TokenStore.importTokens(entries);
  console.log('[Sync] Import erfolgreich:', count, 'Einträge, Version:', version);
  return { count, version };
}

// ---------------------------------------------------------------------------
// Automatischer Sync
// ---------------------------------------------------------------------------

/** Status-Badge im Header aktualisieren. */
function _setStatus(state) {
  const el = document.getElementById('sync-status-badge');
  if (!el) return;
  const states = {
    idle: { text: '🔄 Synced', cls: 'text-green-400' },
    syncing: { text: '⏳ Syncing…', cls: 'text-yellow-400' },
    error: { text: '❌ Sync-Fehler', cls: 'text-red-400' },
    nopw: { text: '🔒 Kein Sync-PW', cls: 'text-gray-500' },
  };
  const s = states[state] || states.idle;
  el.textContent = s.text;
  el.className = `text-xs ${s.cls}`;
}

/**
 * Wird beim App-Start aufgerufen.
 * Lädt den Server-Blob herunter und merged ihn in die lokale IndexedDB.
 * Passiert lautlos falls kein Passwort gesetzt oder kein Blob vorhanden.
 */
async function autoDownload(userId) {
  const pw = getSyncPassword();
  if (!pw) {
    _setStatus('nopw');
    return;
  }
  _setStatus('syncing');
  try {
    const { count, version } = await importFromSync(userId, pw);
    console.log(`[Sync] Auto-Download: ${count} Tokens gemergt (v${version})`);
    _setStatus('idle');
  } catch (err) {
    if (err.message.includes('404') || err.message.includes('vorhanden')) {
      // Noch kein Blob auf Server – kein Fehler, einfach erster Start
      _setStatus('idle');
    } else if (err.message.includes('decrypt') || err.message.includes('GCM')) {
      console.warn('[Sync] Falsches Passwort beim Auto-Download');
      _setStatus('error');
    } else {
      console.warn('[Sync] Auto-Download fehlgeschlagen:', err.message);
      _setStatus('error');
    }
  }
}

/**
 * Plant einen verschlüsselten Upload 2 Sekunden nach dem letzten Aufruf.
 * Wird nach jeder neuen Token-Vergabe aufgerufen (debounced).
 */
function scheduleUpload(userId) {
  if (!hasSyncPassword()) return;
  if (_uploadTimer) clearTimeout(_uploadTimer);
  _uploadTimer = setTimeout(async () => {
    _setStatus('syncing');
    try {
      const pw = getSyncPassword();
      if (!pw) { _setStatus('nopw'); return; }
      await exportAndSync(userId, pw);
      _setStatus('idle');
    } catch (err) {
      console.warn('[Sync] Auto-Upload fehlgeschlagen:', err.message);
      _setStatus('error');
    }
  }, 2000);
}

// ---------------------------------------------------------------------------
// Sync-UI (Einstellungen-Tab)
// ---------------------------------------------------------------------------

function renderSyncUI(containerId, userId) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const hasPw = hasSyncPassword();
  const pwHint = hasPw ? '••••••••' : '';

  el.innerHTML = `
    <div class="flex flex-col gap-4 text-sm">
      <p class="text-gray-400 text-xs">
        Das Token-Wörterbuch (Name↔Token Zuordnung) wird beim Start automatisch geladen
        und nach jeder Änderung automatisch gespeichert – verschlüsselt mit deinem Passwort.
        Das Passwort verlässt deinen Browser nicht.
      </p>

      <div id="sync-pw-section" class="flex flex-col gap-2">
        <label class="text-xs text-gray-400">Sync-Passwort</label>
        <div class="flex gap-2">
          <input id="sync-password" type="password" placeholder="${hasPw ? 'Passwort ändern…' : 'Neues Passwort setzen…'}"
            class="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
          <button onclick="syncSavePassword('${userId}')"
            class="bg-blue-700 hover:bg-blue-600 rounded px-4 py-2 text-sm font-medium whitespace-nowrap">
            ${hasPw ? 'Ändern' : 'Setzen'}
          </button>
        </div>
        ${hasPw ? `<p class="text-xs text-green-400">✅ Passwort gesetzt – Auto-Sync aktiv</p>` : `<p class="text-xs text-yellow-400">⚠️ Kein Passwort – Auto-Sync inaktiv</p>`}
      </div>

      <div class="flex gap-2">
        <button onclick="syncManualExport('${userId}')"
          class="flex-1 bg-gray-700 hover:bg-gray-600 rounded px-3 py-2 text-sm">
          Jetzt hochladen
        </button>
        <button onclick="syncManualImport('${userId}')"
          class="flex-1 bg-gray-700 hover:bg-gray-600 rounded px-3 py-2 text-sm">
          Jetzt herunterladen
        </button>
        ${hasPw ? `<button onclick="syncClearPassword('${userId}')"
          class="bg-red-900 hover:bg-red-800 rounded px-3 py-2 text-sm">
          PW löschen
        </button>` : ''}
      </div>
      <div id="sync-result" class="text-xs min-h-[1.25rem]"></div>
    </div>
  `;
}

// Passwort setzen & sofort ersten Upload auslösen
async function syncSavePassword(userId) {
  const pw = document.getElementById('sync-password')?.value?.trim();
  const res = document.getElementById('sync-result');
  if (!pw || pw.length < 4) {
    if (res) res.innerHTML = '<span class="text-red-400">Bitte mindestens 4 Zeichen eingeben.</span>';
    return;
  }
  setSyncPassword(pw);
  if (res) res.innerHTML = '<span class="text-yellow-400">Passwort gesetzt, lade hoch…</span>';
  try {
    const data = await exportAndSync(userId, pw);
    if (res) res.innerHTML = `<span class="text-green-400">Gespeichert (Version ${data.version}). Auto-Sync ist jetzt aktiv.</span>`;
    _setStatus('idle');
    // UI neu rendern um Status zu aktualisieren
    renderSyncUI('sync-container', userId);
  } catch (e) {
    if (res) res.innerHTML = `<span class="text-red-400">${e.message}</span>`;
  }
}

async function syncManualExport(userId) {
  const res = document.getElementById('sync-result');
  const pw = getSyncPassword();
  if (!pw) { if (res) res.innerHTML = '<span class="text-red-400">Kein Passwort gesetzt.</span>'; return; }
  if (res) res.innerHTML = '<span class="text-gray-400">Lade hoch…</span>';
  try {
    const data = await exportAndSync(userId, pw);
    if (res) res.innerHTML = `<span class="text-green-400">Hochgeladen (Version ${data.version}).</span>`;
    _setStatus('idle');
  } catch (e) {
    if (res) res.innerHTML = `<span class="text-red-400">${e.message}</span>`;
    _setStatus('error');
  }
}

async function syncManualImport(userId) {
  const res = document.getElementById('sync-result');
  const pw = getSyncPassword();
  if (!pw) { if (res) res.innerHTML = '<span class="text-red-400">Kein Passwort gesetzt.</span>'; return; }
  if (res) res.innerHTML = '<span class="text-gray-400">Lade herunter…</span>';
  try {
    const data = await importFromSync(userId, pw);
    if (res) res.innerHTML = `<span class="text-green-400">${data.count} Tokens geladen (v${data.version}).</span>`;
    _setStatus('idle');
  } catch (e) {
    if (res) res.innerHTML = `<span class="text-red-400">${e.message}</span>`;
    _setStatus('error');
  }
}

function syncClearPassword(userId) {
  clearSyncPassword();
  _setStatus('nopw');
  renderSyncUI('sync-container', userId);
}

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

function _bufToBase64(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}

function _base64ToBuf(b64) {
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

window.Sync = {
  exportAndSync,
  importFromSync,
  autoDownload,
  scheduleUpload,
  hasSyncPassword,
  getSyncPassword,
  setSyncPassword,
  renderSyncUI,
};
window.syncSavePassword = syncSavePassword;
window.syncManualExport = syncManualExport;
window.syncManualImport = syncManualImport;
window.syncClearPassword = syncClearPassword;
