"""
Unit Tests für whatsapp_ids.py

Testet das einheitliche ID-Schema für WhatsApp Messages.
"""
import pytest
from backend.ingestion.whatsapp_ids import (
    normalize_sender,
    parse_txt_timestamp,
    generate_message_id,
    parse_txt_line_to_id,
    parse_txt_line
)


class TestNormalizeSender:
    """Tests für Sender-Normalisierung."""

    def test_simple_name(self):
        """Einfache Namen werden lowercase + underscores."""
        assert normalize_sender("Marie Mueller") == "marie_mueller"
        assert normalize_sender("Alex Mueller") == "alex_mueller"

    def test_german_ich(self):
        """'Ich' wird zu 'me'."""
        assert normalize_sender("Ich") == "me"
        assert normalize_sender("ich") == "me"
        assert normalize_sender("ICH") == "me"

    def test_english_me(self):
        """'Me' bleibt 'me'."""
        assert normalize_sender("me") == "me"
        assert normalize_sender("Me") == "me"
        assert normalize_sender("ME") == "me"

    def test_phone_number(self):
        """Telefonnummern werden ohne Suffix normalisiert."""
        assert normalize_sender("491987654321@c.us") == "491987654321"
        assert normalize_sender("491234567890@s.whatsapp.net") == "491234567890"

    def test_group_id(self):
        """Gruppen-IDs werden normalisiert."""
        assert normalize_sender("491604823380-1601037405@g.us") == "491604823380_1601037405"

    def test_newsletter(self):
        """Newsletter-IDs werden normalisiert."""
        assert normalize_sender("120363174430110477@newsletter") == "120363174430110477"

    def test_empty_string(self):
        """Leere Strings werden zu 'unknown'."""
        assert normalize_sender("") == "unknown"
        assert normalize_sender(None) == "unknown"

    def test_special_characters(self):
        """Sonderzeichen werden zu underscores."""
        assert normalize_sender("Marie-Marie") == "sarah_marie"
        assert normalize_sender("Test@User") == "test_user"  # @ wird zu _

    def test_max_length(self):
        """Max 30 Zeichen."""
        long_name = "a" * 50
        result = normalize_sender(long_name)
        assert len(result) == 30


class TestParseTimestamp:
    """Tests für Timestamp-Parsing."""

    def test_format_ddmmyy_hhmm(self):
        """Format: DD.MM.YY HH:MM"""
        assert parse_txt_timestamp("26.04.19 14:42") == 1556282520

    def test_format_with_seconds(self):
        """Format: DD.MM.YY, HH:MM:SS"""
        assert parse_txt_timestamp("26.04.19, 14:42:30") == 1556282550

    def test_with_brackets(self):
        """Timestamps mit Klammern."""
        assert parse_txt_timestamp("[26.04.19 14:42]") == 1556282520
        assert parse_txt_timestamp("[26.04.19, 14:42:30]") == 1556282550

    def test_year_2000_conversion(self):
        """2-stellige Jahre werden zu 20XX."""
        # 19 → 2019
        ts = parse_txt_timestamp("26.04.19 14:42")
        from datetime import datetime
        dt = datetime.fromtimestamp(ts)
        assert dt.year == 2019

    def test_invalid_format_raises_error(self):
        """Ungültige Formate werfen ValueError."""
        with pytest.raises(ValueError):
            parse_txt_timestamp("invalid")
        with pytest.raises(ValueError):
            parse_txt_timestamp("01-02-03 12:34")


class TestGenerateMessageId:
    """Tests für Message-ID Generierung."""

    def test_basic_id(self):
        """Basis-ID ohne Collision-Detection."""
        msg_id = generate_message_id(
            "491987654321@c.us",
            1556282520,
            "Alex"
        )
        assert msg_id == "wa_491987654321@c.us_1556282520_josh"

    def test_with_collision_detection(self):
        """ID mit Message-Content für Collision-Detection."""
        msg_id = generate_message_id(
            "491987654321@c.us",
            1556282520,
            "Alex",
            "Hello there"
        )
        # Sollte Hash anhängen
        assert msg_id.startswith("wa_491987654321@c.us_1556282520_josh_")
        assert len(msg_id) > len("wa_491987654321@c.us_1556282520_josh")

    def test_collision_different_messages(self):
        """Unterschiedliche Messages erzeugen unterschiedliche IDs."""
        id1 = generate_message_id("123@c.us", 1000, "Alex", "Hello")
        id2 = generate_message_id("123@c.us", 1000, "Alex", "World")

        assert id1 != id2
        assert id1.startswith("wa_123@c.us_1000_josh_")
        assert id2.startswith("wa_123@c.us_1000_josh_")

    def test_same_message_same_id(self):
        """Gleiche Message erzeugt gleiche ID."""
        id1 = generate_message_id("123@c.us", 1000, "Alex", "Hello")
        id2 = generate_message_id("123@c.us", 1000, "Alex", "Hello")

        assert id1 == id2

    def test_sender_normalization(self):
        """Sender wird automatisch normalisiert."""
        msg_id = generate_message_id(
            "491987654321@c.us",
            1556282520,
            "Marie Mueller"
        )
        assert msg_id == "wa_491987654321@c.us_1556282520_marie_mueller"


class TestParseTxtLineToId:
    """Tests für komplettes TXT-Line-Parsing zu ID."""

    def test_simple_line(self):
        """Einfache WhatsApp-Zeile."""
        line = "[26.04.19 14:42] Alex: Hi there"
        msg_id = parse_txt_line_to_id(line, "491987654321@c.us")

        assert msg_id is not None
        assert msg_id.startswith("wa_491987654321@c.us_1556282520_josh")

    def test_with_sender_space(self):
        """Sender mit Leerzeichen."""
        line = "[26.04.19 14:42] Marie Mueller: Hello!"
        msg_id = parse_txt_line_to_id(line, "491987654321@c.us")

        assert msg_id is not None
        assert "marie_mueller" in msg_id

    def test_with_seconds(self):
        """Timestamp mit Sekunden."""
        line = "[26.04.19, 14:42:30] Alex: Hi"
        msg_id = parse_txt_line_to_id(line, "491987654321@c.us")

        assert msg_id is not None
        assert msg_id.startswith("wa_491987654321@c.us_1556282550")

    def test_invalid_line_returns_none(self):
        """Ungültige Zeilen returnen None."""
        assert parse_txt_line_to_id("Invalid line", "123@c.us") is None
        assert parse_txt_line_to_id("No brackets here", "123@c.us") is None
        assert parse_txt_line_to_id("", "123@c.us") is None

    def test_media_message(self):
        """Medien-Nachrichten."""
        line = "[26.04.19 14:42] Marie: <Medien ausgeschlossen>"
        msg_id = parse_txt_line_to_id(line, "491987654321@c.us")

        assert msg_id is not None
        assert "sarah" in msg_id


class TestParseTxtLine:
    """Tests für parse_txt_line (zu Dict)."""

    def test_parse_to_dict(self):
        """Parst zu strukturiertem Dict."""
        line = "[26.04.19 14:42] Alex: Hi there"
        result = parse_txt_line(line)

        assert result is not None
        assert result['timestamp'] == 1556282520
        assert result['sender'] == 'Alex'
        assert result['message'] == 'Hi there'

    def test_multiword_sender(self):
        """Sender mit mehreren Worten."""
        line = "[26.04.19 14:42] Marie Mueller: Hello"
        result = parse_txt_line(line)

        assert result is not None
        assert result['sender'] == 'Marie Mueller'

    def test_colon_in_message(self):
        """Doppelpunkt in Nachricht."""
        line = "[26.04.19 14:42] Alex: Time is: 14:42"
        result = parse_txt_line(line)

        assert result is not None
        assert result['message'] == 'Time is: 14:42'

    def test_invalid_returns_none(self):
        """Ungültige Lines returnen None."""
        assert parse_txt_line("Invalid") is None
        assert parse_txt_line("") is None


class TestDeduplication:
    """Integration-Tests für Deduplication zwischen TXT und Live."""

    def test_txt_and_live_same_id(self):
        """TXT-Import und Live-Import erzeugen gleiche ID (ohne Collision)."""
        # TXT-Import
        txt_line = "[26.04.19 14:42] Alex: Hi"
        txt_id = parse_txt_line_to_id(txt_line, "491987654321@c.us")

        # Live-Import (ohne Message-Content)
        live_id = generate_message_id(
            "491987654321@c.us",
            1556282520,
            "Alex"
        )

        # Base-IDs sollten gleich sein (Basis ohne Hash)
        assert live_id == "wa_491987654321@c.us_1556282520_josh"

        # TXT hat Collision-Detection (Hash), Live nicht
        # Daher unterschiedlich, ABER: Live kann mit upsert() überschreiben
        assert txt_id.startswith(live_id)

    def test_different_senders_different_ids(self):
        """Unterschiedliche Sender erzeugen unterschiedliche IDs."""
        id1 = generate_message_id("123@c.us", 1000, "Alex")
        id2 = generate_message_id("123@c.us", 1000, "Marie")

        assert id1 != id2
        assert "josh" in id1
        assert "sarah" in id2

    def test_different_timestamps_different_ids(self):
        """Unterschiedliche Timestamps erzeugen unterschiedliche IDs."""
        id1 = generate_message_id("123@c.us", 1000, "Alex")
        id2 = generate_message_id("123@c.us", 2000, "Alex")

        assert id1 != id2
        assert "1000" in id1
        assert "2000" in id2


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
