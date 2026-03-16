-- memosaur – initiales Datenbankschema
-- Migration 001

-- Nutzer-Tabelle (Single-User-System mit OAuth)
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,          -- UUID v4
    display_name TEXT NOT NULL,
    created_at   INTEGER NOT NULL,          -- Unix timestamp
    is_active    INTEGER NOT NULL DEFAULT 1
);

-- Schema-Versionsprotokoll
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (1, strftime('%s', 'now'));
