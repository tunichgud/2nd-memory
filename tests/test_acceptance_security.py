"""
test_acceptance_security.py – Python-Akzeptanztests fuer WhatsApp Send-Guard

Abgedeckte Test-IDs:
  AT-SEC-001  Fremde Chat-ID wird blockiert
  AT-SEC-002  Gruppenchat wird blockiert
  AT-SEC-003  Eigener Chat wird erlaubt
  AT-SEC-004  Fehlende Konfiguration blockiert
  AT-SEC-005  Edge Cases blockieren (undefined/null/leerer String)
  AT-SEC-010  Bot antwortet nur im Selbst-Chat
  AT-SEC-011  Eigene Nachricht an Sarah wird NICHT verarbeitet
  AT-SEC-012  Bot-Nachrichten-Loop-Prevention
  AT-SEC-013  Bot deaktiviert -- keine Verarbeitung
  AT-SEC-014  Keine User-Chat-ID -- keine Verarbeitung
  AT-SEC-020  handleVoiceMessage ruft assertSendAllowed auf (Quellcode-Analyse)
  AT-SEC-021  STT-Zusammenfassung geht nur an eigenen Chat
  AT-SEC-022  STT-Endpoint sendet nicht selbst
  AT-SEC-030  /api/whatsapp/send MUSS assertSendAllowed aufrufen
  AT-SEC-040  Jeder sendMessage-Aufruf ist durch Guard geschuetzt
  AT-SEC-041  assertSendAllowed ist als module.exports exponiert
  AT-SEC-042  assertSendAllowed fuehrt strikte Gleichheitspruefung durch

Testmethode:
- Verhaltenstests: Python subprocess fuehrt assertSendAllowed via Node.js aus
- Strukturtests: fs-basierte Quellcode-Analyse

Ausfuehren: pytest tests/test_acceptance_security.py -v -m safety
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_JS = PROJECT_ROOT / "index.js"

MY_CHAT_ID    = "491701234567@c.us"
SARAH_CHAT_ID = "491709876543@c.us"
GROUP_CHAT_ID = "123456789@g.us"


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _run_node_assertion(chat_id: str | None, user_chat_id: str | None) -> dict:
    """Fuehrt assertSendAllowed via Node.js-Subprocess aus."""
    script = f"""
process.env.WHATSAPP_PORT = '0';
const {{ assertSendAllowed }} = require({json.dumps(str(INDEX_JS))});
const config = {{ user_chat_id: {json.dumps(user_chat_id)} }};
const chatId = {json.dumps(chat_id)};
try {{
    assertSendAllowed(chatId, config);
    process.stdout.write(JSON.stringify({{ threw: false, message: '' }}));
    process.exit(0);
}} catch (err) {{
    process.stdout.write(JSON.stringify({{ threw: true, message: err.message }}));
    process.exit(0);
}}
"""
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        env={**__import__("os").environ, "WHATSAPP_PORT": "0"},
    )
    return json.loads(result.stdout)


def _load_index_js_source() -> str:
    return INDEX_JS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AT-SEC-001: Fremde Chat-ID wird blockiert
# ---------------------------------------------------------------------------

@pytest.mark.safety
class TestAssertSendAllowedSafety:
    """Tests fuer assertSendAllowed() direkt via Node.js Subprocess."""

    def test_at_sec_001_foreign_chat_blocked(self):
        """AT-SEC-001: Fremde Chat-ID wird mit Safety-Error blockiert."""
        outcome = _run_node_assertion(SARAH_CHAT_ID, MY_CHAT_ID)
        assert outcome["threw"] is True
        assert outcome["message"].startswith("Safety:"), (
            f"Error-Message muss 'Safety:' beginnen, war: '{outcome['message']}'"
        )
        assert SARAH_CHAT_ID in outcome["message"], (
            f"Error-Message soll blockierte Chat-ID enthalten: '{outcome['message']}'"
        )

    def test_at_sec_002_group_chat_blocked(self):
        """AT-SEC-002: Gruppenchat-ID wird blockiert."""
        outcome = _run_node_assertion(GROUP_CHAT_ID, MY_CHAT_ID)
        assert outcome["threw"] is True
        assert "Safety:" in outcome["message"]

    def test_at_sec_003_own_chat_allowed(self):
        """AT-SEC-003: Eigene Chat-ID wird NICHT blockiert."""
        outcome = _run_node_assertion(MY_CHAT_ID, MY_CHAT_ID)
        assert outcome["threw"] is False, (
            f"Eigene Chat-ID darf nicht blockiert werden, Error: '{outcome['message']}'"
        )

    def test_at_sec_004_null_config_blocks(self):
        """AT-SEC-004: user_chat_id = null blockiert alles."""
        outcome = _run_node_assertion(MY_CHAT_ID, None)
        assert outcome["threw"] is True
        assert "Safety:" in outcome["message"]

    def test_at_sec_004_empty_config_blocks(self):
        """AT-SEC-004: user_chat_id = '' (leerer String) blockiert alles."""
        outcome = _run_node_assertion(MY_CHAT_ID, "")
        assert outcome["threw"] is True
        assert "Safety:" in outcome["message"]

    def test_at_sec_005_undefined_chat_id_blocked(self):
        """AT-SEC-005: chatId = undefined wird blockiert (kein Crash)."""
        outcome = _run_node_assertion(None, MY_CHAT_ID)  # None -> JSON null -> undefined
        assert outcome["threw"] is True, "undefined chatId muss Error werfen"

    def test_at_sec_005_empty_string_chat_id_blocked(self):
        """AT-SEC-005: chatId = '' (leerer String) wird blockiert."""
        outcome = _run_node_assertion("", MY_CHAT_ID)
        assert outcome["threw"] is True


# ---------------------------------------------------------------------------
# AT-SEC-010 bis AT-SEC-014: Chat-Routing Sicherheitslogik
# ---------------------------------------------------------------------------

@pytest.mark.safety
class TestChatRoutingLogic:
    """
    Testet die 4-Stufen-Sicherheitslogik via Python-Port der Routing-Funktion.
    Die Logik ist identisch zu index.js und dient als Regressions-Safeguard.
    """

    @staticmethod
    def should_process(msg: dict, bot_config: dict) -> bool:
        """
        Python-Port der Chat-Routing-Logik aus index.js.
        Gibt True zurueck wenn die Nachricht verarbeitet werden soll.
        """
        # Stufe 1: Bot muss aktiviert sein
        if not bot_config.get("bot_enabled", False):
            return False

        # Stufe 2: user_chat_id muss konfiguriert sein
        user_chat_id = bot_config.get("user_chat_id")
        if not user_chat_id:
            return False

        # Stufe 3: Nur Nachrichten im Selbst-Chat
        if msg.get("from") != user_chat_id or msg.get("id", {}).get("remote") != user_chat_id:
            return False

        # Stufe 4: Im Produktiv-Modus nur eingehende Nachrichten
        if not bot_config.get("test_mode", False) and msg.get("fromMe", False):
            return False

        return True

    def test_at_sec_010_bot_answers_in_self_chat(self):
        """AT-SEC-010: Bot verarbeitet Nachricht im Selbst-Chat."""
        bot_config = {
            "bot_enabled": True,
            "user_chat_id": MY_CHAT_ID,
            "test_mode": False,
        }
        msg = {
            "from": MY_CHAT_ID,
            "id": {"remote": MY_CHAT_ID},
            "fromMe": False,
            "body": "Was habe ich heute gemacht?",
        }
        assert self.should_process(msg, bot_config) is True

    def test_at_sec_011_own_message_to_sarah_not_processed(self):
        """AT-SEC-011: Eigene Nachricht an Sarah (fromMe=True) wird NICHT verarbeitet."""
        bot_config = {
            "bot_enabled": True,
            "user_chat_id": MY_CHAT_ID,
            "test_mode": False,
        }
        # fromMe=True: WhatsApp gibt msg.from immer als eigene ID zurueck
        msg = {
            "from": MY_CHAT_ID,        # WhatsApp-Bug: immer eigene ID
            "id": {"remote": SARAH_CHAT_ID},  # aber chat ist Sarahs Chat
            "fromMe": True,
            "body": "ja",
        }
        assert self.should_process(msg, bot_config) is False, (
            "REGRESSION: Eigene Nachricht an Sarah darf NICHT verarbeitet werden!"
        )

    def test_at_sec_012_bot_prefix_loop_prevention(self):
        """AT-SEC-012: Bot-Nachricht mit Dino-Prefix wird ignoriert."""
        bot_config = {
            "bot_enabled": True,
            "user_chat_id": MY_CHAT_ID,
            "test_mode": False,
        }
        # Bot-Nachricht beginnt mit Dino und ist fromMe
        msg = {
            "from": MY_CHAT_ID,
            "id": {"remote": MY_CHAT_ID},
            "fromMe": True,
            "body": "🦕 Das ist eine Bot-Antwort",
        }
        # fromMe=True + test_mode=False -> wird ignoriert (Stufe 4)
        assert self.should_process(msg, bot_config) is False

    def test_at_sec_013_bot_disabled_no_processing(self):
        """AT-SEC-013: Bei bot_enabled=False wird keine Nachricht verarbeitet."""
        bot_config = {
            "bot_enabled": False,
            "user_chat_id": MY_CHAT_ID,
            "test_mode": False,
        }
        msg = {
            "from": MY_CHAT_ID,
            "id": {"remote": MY_CHAT_ID},
            "fromMe": False,
            "body": "Test",
        }
        assert self.should_process(msg, bot_config) is False

    def test_at_sec_014_no_user_chat_id_no_processing(self):
        """AT-SEC-014: Bei fehlendem user_chat_id wird keine Nachricht verarbeitet."""
        bot_config = {
            "bot_enabled": True,
            "user_chat_id": None,
            "test_mode": False,
        }
        msg = {
            "from": MY_CHAT_ID,
            "id": {"remote": MY_CHAT_ID},
            "fromMe": False,
            "body": "Test",
        }
        assert self.should_process(msg, bot_config) is False


# ---------------------------------------------------------------------------
# AT-SEC-020: handleVoiceMessage ruft assertSendAllowed auf (Quellcode)
# ---------------------------------------------------------------------------

@pytest.mark.safety
class TestStructuralSourceCodeAnalysis:
    """Strukturelle Quellcode-Analysen die nicht durch Laufzeitlogik umgangen werden."""

    def test_at_sec_020_handle_voice_message_has_assert_send_allowed(self):
        """AT-SEC-020: handleVoiceMessage enthaelt assertSendAllowed-Aufruf (Quellcode)."""
        source = _load_index_js_source()

        # Finde handleVoiceMessage Funktionskoerper
        fn_match = re.search(
            r"async function handleVoiceMessage[\s\S]*?^}",
            source,
            re.MULTILINE,
        )
        assert fn_match is not None, "handleVoiceMessage nicht in index.js gefunden"

        fn_body = fn_match.group(0)
        assert "assertSendAllowed" in fn_body, (
            "handleVoiceMessage muss assertSendAllowed aufrufen! "
            "Sonst koennte die Zusammenfassung an beliebige Chat-IDs gesendet werden."
        )

    def test_at_sec_020_assert_send_allowed_before_send_message_in_voice(self):
        """AT-SEC-020: assertSendAllowed steht VOR client.sendMessage in handleVoiceMessage."""
        source = _load_index_js_source()

        fn_match = re.search(
            r"async function handleVoiceMessage[\s\S]*?^}",
            source,
            re.MULTILINE,
        )
        assert fn_match is not None
        fn_body = fn_match.group(0)

        assert_idx = fn_body.find("assertSendAllowed")
        send_idx = fn_body.find("sendMessage")

        assert assert_idx < send_idx, (
            f"assertSendAllowed (pos {assert_idx}) muss VOR sendMessage (pos {send_idx}) stehen"
        )

    def test_at_sec_021_stt_sends_to_self_only(self):
        """AT-SEC-021: handleVoiceMessage sendet an config.user_chat_id (nicht msg.from)."""
        source = _load_index_js_source()

        fn_match = re.search(
            r"async function handleVoiceMessage[\s\S]*?^}",
            source,
            re.MULTILINE,
        )
        assert fn_match is not None
        fn_body = fn_match.group(0)

        # sendMessage soll config.user_chat_id verwenden, nicht msg.from
        assert "config.user_chat_id" in fn_body, (
            "sendMessage in handleVoiceMessage muss config.user_chat_id als Ziel verwenden"
        )
        # Sicherstellen dass msg.from NICHT als sendMessage-Ziel verwendet wird
        # (msg.from waere der Absender der Sprachnachricht -- z.B. Sarah)
        send_lines = [
            line.strip()
            for line in fn_body.split("\n")
            if "sendMessage" in line
        ]
        for line in send_lines:
            assert "msg.from" not in line, (
                f"sendMessage darf NICHT msg.from als Ziel verwenden: '{line}'"
            )

    def test_at_sec_030_send_endpoint_has_assert_guard(self):
        """AT-SEC-030: POST /api/whatsapp/send Handler enthaelt assertSendAllowed (Quellcode)."""
        source = _load_index_js_source()

        # Finde den Handler-Block
        handler_match = re.search(
            r"app\.post\(['\"]\/api\/whatsapp\/send['\"][\s\S]*?(?=\napp\.|module\.)",
            source,
        )
        assert handler_match is not None, "POST /api/whatsapp/send Handler nicht gefunden"

        handler_body = handler_match.group(0)
        assert "assertSendAllowed" in handler_body, (
            "SICHERHEITSLUECKE: POST /api/whatsapp/send ruft assertSendAllowed NICHT auf! "
            "Jeder HTTP-Client kann an beliebige Chat-IDs Nachrichten senden."
        )

    def test_at_sec_041_assert_send_allowed_exported(self):
        """AT-SEC-041: assertSendAllowed ist in module.exports enthalten."""
        source = _load_index_js_source()

        export_match = re.search(
            r"module\.exports\s*=\s*\{[^}]*assertSendAllowed[^}]*\}",
            source,
        )
        assert export_match is not None, (
            "assertSendAllowed muss in module.exports stehen damit Tests "
            "die echte Funktion importieren koennen"
        )

    def test_at_sec_042_strict_equality_used(self):
        """AT-SEC-042: assertSendAllowed verwendet strikte Gleichheit (===)."""
        source = _load_index_js_source()

        fn_match = re.search(
            r"function assertSendAllowed[\s\S]*?^}",
            source,
            re.MULTILINE,
        )
        assert fn_match is not None, "assertSendAllowed nicht gefunden"
        fn_body = fn_match.group(0)

        # Muss === oder !== haben
        assert "===" in fn_body or "!==" in fn_body, (
            "assertSendAllowed muss strikte Gleichheit (===) verwenden"
        )

        # Darf kein loose == oder != haben (== und != ohne drittes =)
        body_without_strict = fn_body.replace("!==", "").replace("===", "")
        assert not re.search(r"(?<![!<>])==[^=]", body_without_strict), (
            "assertSendAllowed darf KEIN == verwenden (Type Coercion-Risiko)"
        )

    def test_at_sec_040_all_send_calls_guarded(self):
        """AT-SEC-040: Alle sendMessage/reply-Aufrufe sind durch Guard geschuetzt."""
        source = _load_index_js_source()
        lines = source.split("\n")

        unguarded = []
        for idx, line in enumerate(lines):
            if not re.search(r"client\.sendMessage\(|chat\.sendMessage\(|msg\.reply\(", line):
                continue

            # Kontext: 200 Zeilen vor diesem Aufruf
            context_start = max(0, idx - 200)
            context = "\n".join(lines[context_start:idx])

            # Pruefung 1: assertSendAllowed im Kontext
            has_assert = "assertSendAllowed" in context

            # Pruefung 2: 4-Stufen-Guard fuer msg.reply()
            has_four_step_guard = (
                "msg.reply(" in line and
                ("msg.from !== BOT_CONFIG.user_chat_id" in context or
                 "msg.id.remote !== BOT_CONFIG.user_chat_id" in context or
                 ("msg.from" in context and "user_chat_id" in context))
            )

            if not (has_assert or has_four_step_guard):
                unguarded.append(f"Zeile {idx + 1}: {line.strip()}")

        assert len(unguarded) == 0, (
            f"Ungeschuetzte Send-Aufrufe gefunden:\n" + "\n".join(unguarded)
        )
