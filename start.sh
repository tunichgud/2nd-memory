#!/usr/bin/env bash
# start.sh – memosaur starten

set -e
cd "$(dirname "$0")"

# Virtuelle Umgebung anlegen falls nicht vorhanden
if [ ! -d ".venv" ]; then
  echo "Erstelle virtuelle Python-Umgebung..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Abhängigkeiten installieren
echo "Installiere Abhängigkeiten..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Server starten
echo ""
echo "🦕 memosaur startet auf http://localhost:8000"
echo "   Drücke Ctrl+C zum Beenden."
echo ""

python -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --app-dir "$(pwd)"
