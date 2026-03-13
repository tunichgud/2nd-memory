-- memosaur – Authentication & Session Management
-- Migration 002 (Fixed: SQLite-compatible ALTER TABLE)

-- Erweitere users Tabelle für OAuth
ALTER TABLE users ADD COLUMN google_id TEXT;
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN picture_url TEXT;

-- UNIQUE constraint via Index (SQLite-kompatibel, nur für non-NULL Werte)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL;

-- Passkey-Credentials (WebAuthn)
CREATE TABLE IF NOT EXISTS passkey_credentials (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    counter INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_used_at INTEGER
);

-- Sessions (Cookie-basiert)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    user_agent TEXT,
    ip_hint TEXT  -- anonymisiert: nur letztes Oktet
);

-- Index für schnelle Session-Lookups
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

-- Schema-Version aktualisieren
INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (2, strftime('%s', 'now'));
