-- Migration 002: sync_blobs Tabelle entfernen
DROP TABLE IF EXISTS sync_blobs;

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (2, strftime('%s', 'now'));
