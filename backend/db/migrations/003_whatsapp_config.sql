-- Migration 003: whatsapp_config Tabelle (ersetzt ChromaDB-Storage)
CREATE TABLE IF NOT EXISTS whatsapp_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
