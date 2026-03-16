-- Migration 003: whatsapp_config Tabelle (ersetzt ChromaDB-Storage)
CREATE TABLE IF NOT EXISTS whatsapp_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (3, strftime('%s', 'now'));
