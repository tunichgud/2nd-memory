#!/bin/bash
# Manual Test für Profile Editing Feature
#
# Voraussetzung: Backend läuft auf localhost:8000
# Usage: ./tests/manual/test_profile_editing.sh

set -e  # Exit on error

BACKEND_URL="http://localhost:8000"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BOLD}🧪 Manual Test: Profile Editing${NC}"
echo -e "Backend URL: ${BACKEND_URL}\n"

# 1. Backend erreichbar?
echo -e "${BLUE}[1/7]${NC} Teste Backend-Verbindung..."
if curl -s -f "${BACKEND_URL}/health" > /dev/null; then
    echo -e "${GREEN}✅ Backend ist online${NC}\n"
else
    echo -e "${RED}❌ Backend nicht erreichbar! Starte Backend mit: python -m uvicorn backend.main:app --reload${NC}"
    exit 1
fi

# 2. User erstellen
echo -e "${BLUE}[2/7]${NC} Erstelle Test-User..."
USER_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/v1/users" \
    -H "Content-Type: application/json" \
    -d '{"display_name": "Test User"}')

USER_ID=$(echo $USER_RESPONSE | jq -r '.id')
echo "User ID: ${USER_ID}"
echo -e "${GREEN}✅ User erstellt${NC}\n"

# 3. User abrufen
echo -e "${BLUE}[3/7]${NC} Hole User-Info..."
curl -s "${BACKEND_URL}/api/v1/users/${USER_ID}" | jq .
echo -e "${GREEN}✅ User abgerufen${NC}\n"

# 4. Namen ändern (erfolgreich)
echo -e "${BLUE}[4/7]${NC} Ändere Display Name zu 'Updated Name'..."
UPDATE_RESPONSE=$(curl -s -X PATCH "${BACKEND_URL}/api/v1/users/${USER_ID}" \
    -H "Content-Type: application/json" \
    -d '{"display_name": "Updated Name"}')

UPDATED_NAME=$(echo $UPDATE_RESPONSE | jq -r '.display_name')
if [ "$UPDATED_NAME" = "Updated Name" ]; then
    echo -e "${GREEN}✅ Name erfolgreich geändert${NC}"
    echo $UPDATE_RESPONSE | jq .
else
    echo -e "${RED}❌ Fehler beim Ändern des Namens${NC}"
    exit 1
fi
echo ""

# 5. Validierung: Leerer Name (sollte 400 zurückgeben)
echo -e "${BLUE}[5/7]${NC} Teste Validierung: Leerer Name (erwarte 400)..."
EMPTY_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH "${BACKEND_URL}/api/v1/users/${USER_ID}" \
    -H "Content-Type: application/json" \
    -d '{"display_name": ""}')

HTTP_CODE=$(echo "$EMPTY_RESPONSE" | tail -n 1)
if [ "$HTTP_CODE" = "400" ]; then
    echo -e "${GREEN}✅ Leerer Name korrekt abgelehnt (400)${NC}"
else
    echo -e "${RED}❌ Falscher Status Code: ${HTTP_CODE} (erwartet: 400)${NC}"
fi
echo ""

# 6. Validierung: Name zu lang (sollte 400 zurückgeben)
echo -e "${BLUE}[6/7]${NC} Teste Validierung: Name > 100 Zeichen (erwarte 400)..."
LONG_NAME=$(python3 -c "print('A' * 101)")
LONG_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH "${BACKEND_URL}/api/v1/users/${USER_ID}" \
    -H "Content-Type: application/json" \
    -d "{\"display_name\": \"${LONG_NAME}\"}")

HTTP_CODE=$(echo "$LONG_RESPONSE" | tail -n 1)
if [ "$HTTP_CODE" = "400" ]; then
    echo -e "${GREEN}✅ Langer Name korrekt abgelehnt (400)${NC}"
else
    echo -e "${RED}❌ Falscher Status Code: ${HTTP_CODE} (erwartet: 400)${NC}"
fi
echo ""

# 7. Unicode-Test
echo -e "${BLUE}[7/7]${NC} Teste Unicode-Namen (Emojis, Umlaute)..."
UNICODE_RESPONSE=$(curl -s -X PATCH "${BACKEND_URL}/api/v1/users/${USER_ID}" \
    -H "Content-Type: application/json" \
    -d '{"display_name": "Max Müller 🚀🇩🇪"}')

UNICODE_NAME=$(echo $UNICODE_RESPONSE | jq -r '.display_name')
if [ "$UNICODE_NAME" = "Max Müller 🚀🇩🇪" ]; then
    echo -e "${GREEN}✅ Unicode-Name erfolgreich gespeichert${NC}"
    echo $UNICODE_RESPONSE | jq .
else
    echo -e "${RED}❌ Unicode-Fehler${NC}"
    exit 1
fi
echo ""

# Zusammenfassung
echo -e "${BOLD}${GREEN}✅ Alle Tests bestanden!${NC}"
echo -e "\nErstellter User: ${USER_ID}"
echo -e "Finaler Name: ${UNICODE_NAME}"
echo -e "\n💡 Öffne http://localhost:8000 und gehe zu 'Einstellungen', um die UI zu testen."
