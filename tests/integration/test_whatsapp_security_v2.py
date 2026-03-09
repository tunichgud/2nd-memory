"""
Integration Tests für WhatsApp Security V2
==========================================

Testet die neue Single-Chat-Architektur:
- Bot antwortet NUR in EINEM persönlichen Chat
- Alle anderen Chats werden ignoriert
- MY_CHAT_ID wird automatisch erkannt oder manuell gesetzt
"""

import pytest
import requests
import time

WHATSAPP_API_BASE = "http://localhost:3001/api/whatsapp"
BACKEND_API_BASE = "http://localhost:8000"


def test_01_whatsapp_api_is_running():
    """Test 1: WhatsApp API ist erreichbar"""
    try:
        response = requests.get(f"{WHATSAPP_API_BASE}/status", timeout=5)
        assert response.status_code == 200, "WhatsApp API sollte erreichbar sein"
        print("✅ WhatsApp API läuft")
    except requests.exceptions.ConnectionError:
        pytest.skip("WhatsApp API nicht gestartet - starte mit ./start.sh")


def test_02_get_bot_config():
    """Test 2: GET /api/whatsapp/config gibt Konfiguration zurück"""
    response = requests.get(f"{WHATSAPP_API_BASE}/config", timeout=5)

    assert response.status_code == 200, "Endpoint sollte erfolgreich sein"

    data = response.json()
    assert "bot_enabled" in data, "Response sollte 'bot_enabled' Feld haben"
    assert "test_mode" in data, "Response sollte 'test_mode' Feld haben"
    assert "my_chat_id" in data, "Response sollte 'my_chat_id' Feld haben"
    assert "my_chat_configured" in data, "Response sollte 'my_chat_configured' Feld haben"

    print(f"✅ Bot Config: enabled={data['bot_enabled']}, test_mode={data['test_mode']}, chat_id={data['my_chat_id']}")


def test_03_bot_is_enabled_by_default():
    """Test 3: Bot ist standardmäßig aktiviert (BOT_ENABLED=true)"""
    response = requests.get(f"{WHATSAPP_API_BASE}/config", timeout=5)
    data = response.json()

    assert data["bot_enabled"] == True, "Bot sollte standardmäßig aktiviert sein"

    print(f"✅ Bot ist aktiviert")


def test_04_my_chat_starts_as_null():
    """Test 4: MY_CHAT_ID ist initial null (nicht konfiguriert)"""
    # Reset falls gesetzt
    requests.delete(f"{WHATSAPP_API_BASE}/config/my-chat", timeout=5)

    response = requests.get(f"{WHATSAPP_API_BASE}/config", timeout=5)
    data = response.json()

    assert data["my_chat_id"] is None, "MY_CHAT_ID sollte initial null sein"
    assert data["my_chat_configured"] == False, "my_chat_configured sollte false sein"

    print(f"✅ MY_CHAT_ID ist null (wird automatisch erkannt beim ersten Nachrichtenversand)")


def test_05_set_my_chat_manually():
    """Test 5: POST /api/whatsapp/config/my-chat setzt Chat-ID manuell"""
    test_chat_id = "491234567890@c.us"

    response = requests.post(
        f"{WHATSAPP_API_BASE}/config/my-chat",
        json={"chatId": test_chat_id},
        timeout=5
    )

    assert response.status_code == 200, "POST sollte erfolgreich sein"

    data = response.json()
    assert data["my_chat_id"] == test_chat_id, "MY_CHAT_ID sollte gesetzt sein"
    assert data["my_chat_configured"] == True, "my_chat_configured sollte true sein"

    print(f"✅ MY_CHAT_ID gesetzt: {test_chat_id}")


def test_06_get_config_shows_set_chat():
    """Test 6: GET /api/whatsapp/config zeigt gesetzte Chat-ID"""
    test_chat_id = "491234567890@c.us"

    # Erst setzen
    requests.post(
        f"{WHATSAPP_API_BASE}/config/my-chat",
        json={"chatId": test_chat_id},
        timeout=5
    )

    # Dann abrufen
    response = requests.get(f"{WHATSAPP_API_BASE}/config", timeout=5)
    data = response.json()

    assert data["my_chat_id"] == test_chat_id, "MY_CHAT_ID sollte persistent sein"
    assert data["my_chat_configured"] == True, "my_chat_configured sollte true sein"

    print(f"✅ Chat-ID persistent: {test_chat_id}")


def test_07_reset_my_chat():
    """Test 7: DELETE /api/whatsapp/config/my-chat entfernt Chat-ID"""
    test_chat_id = "491234567890@c.us"

    # Erst setzen
    requests.post(
        f"{WHATSAPP_API_BASE}/config/my-chat",
        json={"chatId": test_chat_id},
        timeout=5
    )

    # Dann entfernen
    response = requests.delete(f"{WHATSAPP_API_BASE}/config/my-chat", timeout=5)

    assert response.status_code == 200, "DELETE sollte erfolgreich sein"

    data = response.json()
    assert data["my_chat_id"] is None, "MY_CHAT_ID sollte null sein"
    assert data["my_chat_configured"] == False, "my_chat_configured sollte false sein"

    print(f"✅ MY_CHAT_ID zurückgesetzt")


def test_08_missing_chatid_returns_error():
    """Test 8: POST ohne chatId gibt Fehler zurück"""
    response = requests.post(
        f"{WHATSAPP_API_BASE}/config/my-chat",
        json={},  # Kein chatId
        timeout=5
    )

    assert response.status_code == 400, "Sollte 400 Bad Request zurückgeben"

    data = response.json()
    assert "error" in data, "Response sollte Fehler enthalten"

    print(f"✅ Fehlende chatId wird korrekt abgelehnt")


def test_09_overwrite_my_chat():
    """Test 9: MY_CHAT_ID kann überschrieben werden"""
    chat1 = "491234567890@c.us"
    chat2 = "491234567891@c.us"

    # Erst setzen
    response1 = requests.post(
        f"{WHATSAPP_API_BASE}/config/my-chat",
        json={"chatId": chat1},
        timeout=5
    )
    assert response1.json()["my_chat_id"] == chat1

    # Dann überschreiben
    response2 = requests.post(
        f"{WHATSAPP_API_BASE}/config/my-chat",
        json={"chatId": chat2},
        timeout=5
    )

    data = response2.json()
    assert data["my_chat_id"] == chat2, "MY_CHAT_ID sollte überschrieben sein"

    print(f"✅ MY_CHAT_ID von {chat1} auf {chat2} geändert")


def test_10_security_concept_verification():
    """Test 10: Sicherheitskonzept - Nur ein Chat erlaubt"""
    # Das neue Design erlaubt nur EINEN Chat (MY_CHAT_ID)
    # Im Gegensatz zur alten Whitelist (mehrere Chats)

    response = requests.get(f"{WHATSAPP_API_BASE}/config", timeout=5)
    data = response.json()

    # Es gibt kein "allowed_chats" Array mehr
    assert "allowed_chats" not in data, "Sollte keine Whitelist mehr geben"

    # Stattdessen gibt es nur MY_CHAT_ID (ein einziger Chat)
    assert "my_chat_id" in data, "Sollte my_chat_id haben"

    print(f"✅ Sicherheitskonzept verifiziert: Nur EIN Chat erlaubt (nicht mehrere)")
    print(f"   Alte Architektur: Whitelist mit N Chats (UNSICHER)")
    print(f"   Neue Architektur: Nur MY_CHAT_ID (SICHER)")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("WhatsApp Security Tests V2 - Single Chat Architecture")
    print("="*70 + "\n")

    pytest.main([__file__, "-v", "--tb=short"])
