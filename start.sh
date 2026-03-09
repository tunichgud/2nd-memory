#!/usr/bin/env bash
# start.sh – memosaur starten (Backend + WhatsApp)

set -e
cd "$(dirname "$0")"

# Farben für Output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Cleanup Funktion
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    [ ! -z "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null || true
    [ ! -z "$WHATSAPP_PID" ] && kill $WHATSAPP_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Virtuelle Umgebung anlegen falls nicht vorhanden
if [ ! -d ".venv" ]; then
  echo "Erstelle virtuelle Python-Umgebung..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Python Abhängigkeiten installieren
echo "Installiere Python-Abhängigkeiten..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Node.js Abhängigkeiten prüfen (für WhatsApp)
ENABLE_WHATSAPP=false
if command -v node &> /dev/null; then
    if [ ! -d "node_modules" ]; then
        echo "Installiere Node.js-Abhängigkeiten..."
        npm install
    fi
    ENABLE_WHATSAPP=true
fi

# Logs-Verzeichnis erstellen
mkdir -p logs

# Server starten
echo ""
echo -e "${GREEN}🦕 memosaur startet...${NC}"
echo ""

# Backend starten
echo -e "${BLUE}[1/2]${NC} Starting Backend..."
python -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --app-dir "$(pwd)" \
  > logs/backend.log 2>&1 &
BACKEND_PID=$!

# Kurz warten bis Backend läuft
sleep 2

# WhatsApp-Brücke starten (falls Node.js verfügbar)
if [ "$ENABLE_WHATSAPP" = true ]; then
    echo -e "${BLUE}[2/2]${NC} Starting WhatsApp Bridge..."
    node index.js > logs/whatsapp.log 2>&1 &
    WHATSAPP_PID=$!
    echo ""
    echo -e "${GREEN}✓${NC} Backend:  http://localhost:8000 (PID: $BACKEND_PID)"
    echo -e "${GREEN}✓${NC} WhatsApp: Active (PID: $WHATSAPP_PID)"
    echo ""
    echo -e "${YELLOW}First run?${NC} Scan QR code: tail -f logs/whatsapp.log"
else
    echo -e "${YELLOW}[!]${NC} WhatsApp disabled (Node.js not found)"
    echo ""
    echo -e "${GREEN}✓${NC} Backend: http://localhost:8000 (PID: $BACKEND_PID)"
fi

echo ""
echo -e "${BLUE}Logs:${NC}"
echo "  Backend:  tail -f logs/backend.log"
echo "  WhatsApp: tail -f logs/whatsapp.log"
echo ""
echo -e "${YELLOW}Press CTRL+C to stop all services${NC}"
echo ""

# Keep running and monitor
while true; do
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${YELLOW}Backend crashed! Check logs/backend.log${NC}"
        cleanup
    fi
    if [ "$ENABLE_WHATSAPP" = true ] && ! kill -0 $WHATSAPP_PID 2>/dev/null; then
        echo -e "${YELLOW}WhatsApp crashed! Check logs/whatsapp.log${NC}"
        cleanup
    fi
    sleep 5
done
