#!/usr/bin/env bash
# ==============================================================================
# backup_es.sh — Erstellt einen Elasticsearch-Snapshot für memosaur
#
# Voraussetzungen:
#   - Elasticsearch läuft unter http://localhost:9200 (via docker compose up -d)
#   - Das Snapshot-Verzeichnis ist in docker-compose.yaml eingebunden:
#       ./data/es_snapshots:/usr/share/elasticsearch/snapshots
#   - ES wurde mit path.repo=/usr/share/elasticsearch/snapshots gestartet
#
# Nutzung:
#   ./scripts/backup_es.sh
#
# Snapshot-Namen: memosaur_backup_YYYYMMDD
# Gespeichert in: ./data/es_snapshots/
#
# Idempotent: Das Repository wird nur registriert falls noch nicht vorhanden.
#             Ein bereits vorhandener Snapshot des heutigen Tages wird überschrieben.
# ==============================================================================

set -euo pipefail

ES_HOST="${ES_HOST:-http://localhost:9200}"
REPO_NAME="memosaur_snapshots"
SNAPSHOT_NAME="memosaur_backup_$(date +%Y%m%d)"

echo "[backup_es] Ziel: ${ES_HOST}"

# --- 1. Snapshot-Repository registrieren (idempotent) -----------------------
echo "[backup_es] Registriere Snapshot-Repository '${REPO_NAME}'..."

REPO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "${ES_HOST}/_snapshot/${REPO_NAME}")

if [ "${REPO_STATUS}" = "200" ]; then
  echo "[backup_es] Repository '${REPO_NAME}' ist bereits registriert."
else
  curl -s -X PUT "${ES_HOST}/_snapshot/${REPO_NAME}" \
    -H "Content-Type: application/json" \
    -d '{
      "type": "fs",
      "settings": {
        "location": "/usr/share/elasticsearch/snapshots",
        "compress": true
      }
    }' | python3 -m json.tool
  echo "[backup_es] Repository registriert."
fi

# --- 2. Snapshot erstellen --------------------------------------------------
echo "[backup_es] Erstelle Snapshot '${SNAPSHOT_NAME}'..."

curl -s -X PUT "${ES_HOST}/_snapshot/${REPO_NAME}/${SNAPSHOT_NAME}?wait_for_completion=true" \
  -H "Content-Type: application/json" \
  -d '{
    "indices": "memosaur_*",
    "ignore_unavailable": true,
    "include_global_state": false
  }' | python3 -m json.tool

echo "[backup_es] Snapshot '${SNAPSHOT_NAME}' abgeschlossen."
echo "[backup_es] Gespeichert in: ./data/es_snapshots/"
