-- memosaur – initiales Datenbankschema
-- Migration 001

-- Nutzer-Tabelle (Basis für Multi-User-Betrieb)
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,          -- UUID v4
    display_name TEXT NOT NULL,
    created_at   INTEGER NOT NULL,          -- Unix timestamp
    is_active    INTEGER NOT NULL DEFAULT 1
);

-- DSGVO-Einwilligungen (Art. 9 DSGVO)
-- scope: 'biometric_photos' | 'gps' | 'messages'
CREATE TABLE IF NOT EXISTS consents (
    user_id    TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope      TEXT    NOT NULL,
    granted    INTEGER NOT NULL DEFAULT 0,  -- 1 = erteilt, 0 = verweigert
    granted_at INTEGER,                     -- Unix timestamp der letzten Änderung
    ip_hint    TEXT,                        -- anonymisiert: nur letztes Oktet
    PRIMARY KEY (user_id, scope)
);

-- Verschlüsselte Sync-Blobs (Token↔Klarname Wörterbuch)
CREATE TABLE IF NOT EXISTS sync_blobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_hint TEXT,                       -- z.B. "Firefox/Linux" (User-Agent, anonymisiert)
    blob        BLOB    NOT NULL,           -- AES-GCM verschlüsselter Blob (ArrayBuffer)
    iv          TEXT    NOT NULL,           -- Base64-kodierter IV (12 Bytes)
    created_at  INTEGER NOT NULL,           -- Unix timestamp
    version     INTEGER NOT NULL DEFAULT 1  -- Versionszähler pro User
);

-- Index für schnelle Abfragen auf den neuesten Blob pro User
CREATE INDEX IF NOT EXISTS idx_sync_blobs_user_version
    ON sync_blobs (user_id, version DESC);

-- Schema-Versionsprotokoll
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (1, strftime('%s', 'now'));
