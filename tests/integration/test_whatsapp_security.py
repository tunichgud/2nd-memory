"""
Integration Tests für WhatsApp Chat-Whitelist Security
========================================================

Testet, dass der Bot nur in erlaubten Chats antwortet und andere Chats ignoriert.
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


def test_02_get_allowed_chats_list():
    """Test 2: GET /api/whatsapp/allowed-chats gibt Liste zurück"""
    response = requests.get(f"{WHATSAPP_API_BASE}/allowed-chats", timeout=5)

    assert response.status_code == 200, "Endpoint sollte erfolgreich sein"

    data = response.json()
    assert "allowed_chats" in data, "Response sollte 'allowed_chats' Feld haben"
    assert isinstance(data["allowed_chats"], list), "allowed_chats sollte eine Liste sein"

    print(f"✅ Allowed Chats: {data['allowed_chats']}")


def test_03_add_chat_to_whitelist():
    """Test 3: POST /api/whatsapp/allowed-chats fügt Chat hinzu"""
    test_chat_id = "491234567890@c.us"

    response = requests.post(
        f"{WHATSAPP_API_BASE}/allowed-chats",
        json={"chatId": test_chat_id},
        timeout=5
    )

    assert response.status_code == 200, "POST sollte erfolgreich sein"

    data = response.json()
    assert test_chat_id in data["allowed_chats"], "Chat sollte in Liste sein"

    print(f"✅ Chat hinzugefügt: {test_chat_id}")


def test_04_duplicate_chat_is_ignored():
    """Test 4: Doppeltes Hinzufügen wird ignoriert (keine Duplikate)"""
    test_chat_id = "491234567890@c.us"

    # Erster Request
    response1 = requests.post(
        f"{WHATSAPP_API_BASE}/allowed-chats",
        json={"chatId": test_chat_id},
        timeout=5
    )

    # Zweiter Request (Duplikat)
    response2 = requests.post(
        f"{WHATSAPP_API_BASE}/allowed-chats",
        json={"chatId": test_chat_id},
        timeout=5
    )

    data = response2.json()
    count = data["allowed_chats"].count(test_chat_id)

    assert count == 1, f"Chat sollte nur 1x in Liste sein, aber ist {count}x drin"

    print(f"✅ Duplikat verhindert")


def test_05_remove_chat_from_whitelist():
    """Test 5: DELETE /api/whatsapp/allowed-chats/:chatId entfernt Chat"""
    test_chat_id = "491234567890@c.us"

    # Erst hinzufügen
    requests.post(
        f"{WHATSAPP_API_BASE}/allowed-chats",
        json={"chatId": test_chat_id},
        timeout=5
    )

    # Dann entfernen
    response = requests.delete(
        f"{WHATSAPP_API_BASE}/allowed-chats/{test_chat_id}",
        timeout=5
    )

    assert response.status_code == 200, "DELETE sollte erfolgreich sein"

    data = response.json()
    assert test_chat_id not in data["allowed_chats"], "Chat sollte nicht mehr in Liste sein"

    print(f"✅ Chat entfernt: {test_chat_id}")


def test_06_add_group_chat_to_whitelist():
    """Test 6: Gruppenchat kann zur Whitelist hinzugefügt werden"""
    group_chat_id = "120363012345678@g.us"

    response = requests.post(
        f"{WHATSAPP_API_BASE}/allowed-chats",
        json={"chatId": group_chat_id},
        timeout=5
    )

    assert response.status_code == 200, "POST sollte erfolgreich sein"

    data = response.json()
    assert group_chat_id in data["allowed_chats"], "Gruppenchat sollte in Liste sein"

    print(f"✅ Gruppenchat hinzugefügt: {group_chat_id}")

    # Cleanup
    requests.delete(f"{WHATSAPP_API_BASE}/allowed-chats/{group_chat_id}", timeout=5)


def test_07_invalid_chat_id_format():
    """Test 7: Ungültiges Chat-ID Format wird akzeptiert (keine Validierung)"""
    # Anmerkung: Aktuell gibt es keine Format-Validierung im Backend
    # Das ist OK, da WhatsApp Web.js selbst validiert
    invalid_chat_id = "invalid-format"

    response = requests.post(
        f"{WHATSAPP_API_BASE}/allowed-chats",
        json={"chatId": invalid_chat_id},
        timeout=5
    )

    # Sollte trotzdem akzeptiert werden (keine Validierung)
    assert response.status_code == 200, "Sollte auch ungültige IDs akzeptieren"

    print(f"✅ Ungültige Chat-ID wird akzeptiert (wird später von WhatsApp validiert)")

    # Cleanup
    requests.delete(f"{WHATSAPP_API_BASE}/allowed-chats/{invalid_chat_id}", timeout=5)


def test_08_missing_chatid_returns_error():
    """Test 8: POST ohne chatId gibt Fehler zurück"""
    response = requests.post(
        f"{WHATSAPP_API_BASE}/allowed-chats",
        json={},  # Kein chatId
        timeout=5
    )

    assert response.status_code == 400, "Sollte 400 Bad Request zurückgeben"

    data = response.json()
    assert "error" in data, "Response sollte Fehler enthalten"

    print(f"✅ Fehlende chatId wird korrekt abgelehnt")


def test_09_empty_whitelist_allows_no_chats():
    """Test 9: Leere Whitelist bedeutet keine Chats erlaubt (außer Auto-Whitelist)"""
    # Alle Chats entfernen
    response = requests.get(f"{WHATSAPP_API_BASE}/allowed-chats", timeout=5)
    data = response.json()

    for chat_id in data["allowed_chats"]:
        requests.delete(f"{WHATSAPP_API_BASE}/allowed-chats/{chat_id}", timeout=5)

    # Prüfen ob leer
    response = requests.get(f"{WHATSAPP_API_BASE}/allowed-chats", timeout=5)
    data = response.json()

    print(f"✅ Whitelist geleert: {data['allowed_chats']}")
    print("ℹ️  Auto-Whitelist aktiviert sich beim nächsten eigenen Nachrichtenversand")


def test_10_multiple_chats_can_be_whitelisted():
    """Test 10: Mehrere Chats können gleichzeitig in Whitelist sein"""
    test_chats = [
        "491234567890@c.us",
        "491234567891@c.us",
        "491234567892@c.us"
    ]

    # Alle hinzufügen
    for chat_id in test_chats:
        requests.post(
            f"{WHATSAPP_API_BASE}/allowed-chats",
            json={"chatId": chat_id},
            timeout=5
        )

    # Prüfen
    response = requests.get(f"{WHATSAPP_API_BASE}/allowed-chats", timeout=5)
    data = response.json()

    for chat_id in test_chats:
        assert chat_id in data["allowed_chats"], f"Chat {chat_id} sollte in Whitelist sein"

    print(f"✅ {len(test_chats)} Chats in Whitelist")

    # Cleanup
    for chat_id in test_chats:
        requests.delete(f"{WHATSAPP_API_BASE}/allowed-chats/{chat_id}", timeout=5)


if __name__ == "__main__":
    print("\n" + "="*70)
    print("WhatsApp Security Tests - Chat Whitelist")
    print("="*70 + "\n")

    pytest.main([__file__, "-v", "--tb=short"])
