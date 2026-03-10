-- memosaur – Local Authentication (Username/Password)
-- Migration 003

-- Erweitere users Tabelle für lokale Authentifizierung
ALTER TABLE users ADD COLUMN username TEXT;
ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0;

-- UNIQUE constraint via Index (SQLite-kompatibel, nur für non-NULL Werte)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL;

-- Schema-Version aktualisieren
INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (3, strftime('%s', 'now'));
