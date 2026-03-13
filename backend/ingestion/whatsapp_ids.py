"""
Einheitliches ID-Schema für alle WhatsApp-Quellen.

Generiert deterministische Message-IDs basierend auf:
- chat_id (WhatsApp-Nummer oder Gruppen-ID)
- timestamp (Unix seconds)
- sender (normalisiert)

Ziel: TXT-Import und Live-Import erzeugen identische IDs
      für die gleiche Nachricht → Automatische Deduplication!
"""
import hashlib
import re
from datetime import datetime
from typing import Optional, Dict, Any


def normalize_sender(sender: str) -> str:
    """
    Normalisiert Sender-Namen für ID-Generierung.

    Args:
        sender: Sender-Name (z.B. "Marie Mueller", "491987654321@c.us", "Ich")

    Returns:
        Normalisierter Sender (z.B. "marie_mueller", "491987654321", "me")

    Examples:
        >>> normalize_sender("Marie Mueller")
        'marie_mueller'
        >>> normalize_sender("Ich")
        'me'
        >>> normalize_sender("491987654321@c.us")
        '491987654321'
    """
    if not sender:
        return 'unknown'

    sender = sender.strip()

    # Deutsche Spezialfälle
    if sender.lower() in ['ich', 'me', 'you']:
        return 'me'

    sender = sender.lower()
    sender = sender.replace(' ', '_')

    # Entferne WhatsApp-Suffixe
    sender = sender.replace('@c.us', '').replace('@g.us', '').replace('@s.whatsapp.net', '')
    sender = sender.replace('@newsletter', '')

    # Nur alphanumerisch + underscore
    sender = ''.join(c if c.isalnum() or c == '_' else '_' for c in sender)

    # Remove multiple consecutive underscores
    sender = re.sub(r'_+', '_', sender)
    sender = sender.strip('_')

    return sender[:30]  # Max 30 chars


def parse_txt_timestamp(date_str: str) -> int:
    """
    Parst WhatsApp TXT-Format Timestamp zu Unix timestamp.

    Args:
        date_str: Datum im WhatsApp-Format (z.B. "26.04.19 14:42", "[26.04.19, 14:42:30]")

    Returns:
        Unix timestamp (Sekunden seit 1970-01-01)

    Raises:
        ValueError: Wenn Format nicht erkannt wird

    Examples:
        >>> parse_txt_timestamp("26.04.19 14:42")
        1556282520
        >>> parse_txt_timestamp("[26.04.19, 14:42:30]")
        1556282550
    """
    # Remove brackets und extra whitespace
    date_str = date_str.strip('[]').strip()

    # Parse verschiedene Formate
    formats = [
        "%d.%m.%y %H:%M",       # 26.04.19 14:42
        "%d.%m.%y, %H:%M:%S",   # 26.04.19, 14:42:30
        "%d.%m.%y, %H:%M",      # 26.04.19, 14:42
        "%d.%m.%Y %H:%M",       # 26.04.2019 14:42
        "%d.%m.%Y, %H:%M:%S",   # 26.04.2019, 14:42:30
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Jahr 2000+ falls 2-stellig
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return int(dt.timestamp())
        except ValueError:
            continue

    raise ValueError(f"Could not parse timestamp: {date_str}")


def generate_message_id(
    chat_id: str,
    timestamp: int,
    sender: str,
    message_content: Optional[str] = None
) -> str:
    """
    Generiert deterministische Message-ID.

    Args:
        chat_id: WhatsApp Chat-ID (z.B. "491987654321@c.us")
        timestamp: Unix timestamp (Sekunden)
        sender: Sender-Name oder Nummer
        message_content: Optional, für Collision-Detection bei gleicher Sekunde

    Returns:
        Einheitliche ID (z.B. "wa_491987654321@c.us_1556282520_josh")

    Examples:
        >>> generate_message_id("491987654321@c.us", 1556282520, "Alex")
        'wa_491987654321@c.us_1556282520_josh'
        >>> generate_message_id("123@c.us", 1000, "Alex", "Hello")
        'wa_123@c.us_1000_josh_5d41402a'
    """
    sender_norm = normalize_sender(sender)
    base_id = f"wa_{chat_id}_{timestamp}_{sender_norm}"

    # Collision detection (optional)
    # Bei 2 Messages in gleicher Sekunde vom gleichen Sender
    if message_content:
        content_hash = hashlib.md5(message_content[:30].encode('utf-8')).hexdigest()[:8]
        return f"{base_id}_{content_hash}"

    return base_id


def parse_txt_line_to_id(line: str, chat_id: str) -> Optional[str]:
    """
    Parst WhatsApp TXT-Zeile direkt zu Message-ID.

    Args:
        line: Zeile aus WhatsApp TXT-Export (z.B. "[26.04.19 14:42] Alex: Hi there")
        chat_id: WhatsApp Chat-ID (z.B. "491987654321@c.us")

    Returns:
        Message-ID oder None bei Parse-Fehler

    Examples:
        >>> parse_txt_line_to_id("[26.04.19 14:42] Alex: Hi", "491987654321@c.us")
        'wa_491987654321@c.us_1556282520_josh'
        >>> parse_txt_line_to_id("Invalid line", "123@c.us")
        None
    """
    # WhatsApp Format: [DD.MM.YY HH:MM] Sender: Message
    # Oder: [DD.MM.YY, HH:MM:SS] Sender: Message
    pattern = r'\[([^\]]+)\]\s*([^:]+):\s*(.+)'
    match = re.match(pattern, line)

    if not match:
        return None

    date_str, sender, message = match.groups()

    try:
        timestamp = parse_txt_timestamp(date_str)
        # Mit message_content für Collision-Detection
        return generate_message_id(chat_id, timestamp, sender, message)
    except (ValueError, Exception):
        return None


def parse_txt_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parst WhatsApp TXT-Zeile zu strukturierten Daten.

    Args:
        line: Zeile aus WhatsApp TXT-Export

    Returns:
        Dict mit timestamp, sender, message oder None

    Examples:
        >>> parse_txt_line("[26.04.19 14:42] Alex: Hi there")
        {'timestamp': 1556282520, 'sender': 'Alex', 'message': 'Hi there'}
    """
    pattern = r'\[([^\]]+)\]\s*([^:]+):\s*(.+)'
    match = re.match(pattern, line)

    if not match:
        return None

    date_str, sender, message = match.groups()

    try:
        timestamp = parse_txt_timestamp(date_str)
        return {
            'timestamp': timestamp,
            'sender': sender.strip(),
            'message': message.strip()
        }
    except (ValueError, Exception):
        return None


# ============================================
# Self-Tests (inline für schnelles Debugging)
# ============================================

def _run_self_tests():
    """Führt Self-Tests aus (nur für Entwicklung)."""

    print("🧪 Running self-tests...")

    # Test 1: Sender-Normalisierung
    assert normalize_sender("Marie Mueller") == "marie_mueller"
    assert normalize_sender("Ich") == "me"
    assert normalize_sender("491987654321@c.us") == "491987654321"
    assert normalize_sender("Alex Mueller") == "josh_bacher"
    print("✅ Test 1: Sender normalization")

    # Test 2: Timestamp-Parsing
    assert parse_txt_timestamp("26.04.19 14:42") == 1556282520
    assert parse_txt_timestamp("[26.04.19 14:42]") == 1556282520
    print("✅ Test 2: Timestamp parsing")

    # Test 3: ID-Generierung
    msg_id = generate_message_id("491987654321@c.us", 1556282520, "Alex")
    assert msg_id == "wa_491987654321@c.us_1556282520_josh"
    print("✅ Test 3: Message ID generation")

    # Test 4: Collision detection
    id1 = generate_message_id("123@c.us", 1000, "Alex", "Hello")
    id2 = generate_message_id("123@c.us", 1000, "Alex", "World")
    assert id1 != id2, f"Expected different IDs, got {id1} and {id2}"
    assert id1.startswith("wa_123@c.us_1000_josh_")
    print("✅ Test 4: Collision detection")

    # Test 5: TXT-Line parsing
    line = "[26.04.19 14:42] Alex: Hi there"
    msg_id = parse_txt_line_to_id(line, "491987654321@c.us")
    assert msg_id is not None
    assert msg_id.startswith("wa_491987654321@c.us_1556282520_josh")
    print("✅ Test 5: TXT line parsing")

    # Test 6: Parse txt line to dict
    parsed = parse_txt_line("[26.04.19 14:42] Alex: Hi there")
    assert parsed is not None
    assert parsed['timestamp'] == 1556282520
    assert parsed['sender'] == 'Alex'
    assert parsed['message'] == 'Hi there'
    print("✅ Test 6: TXT line to dict")

    print("\n🎉 All self-tests passed!")


if __name__ == "__main__":
    _run_self_tests()
