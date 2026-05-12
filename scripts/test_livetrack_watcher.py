import email
import email.policy
import os
import unittest
from unittest.mock import patch
from pathlib import Path

from livetrack_watcher import (
    Config,
    StateStore,
    extract_livetrack_link_from_message,
    is_garmin_livetrack,
    process_unseen_messages,
)


def load_sample() -> object:
    raw = (
        b"From: Garmin <noreply@garmin.com>\n"
        b"Subject: LiveTrack Update\n"
        b"Message-ID: <test-message-id>\n"
        b"Content-Type: text/plain; charset=utf-8\n"
        b"\n"
        b"Track here: https://livetrack.garmin.com/session/example123\n"
    )
    return email.message_from_bytes(raw, policy=email.policy.default)


class LiveTrackWatcherTests(unittest.TestCase):
    def test_detects_garmin_livetrack_email(self) -> None:
        msg = load_sample()
        self.assertTrue(is_garmin_livetrack(msg))

    def test_extracts_livetrack_url(self) -> None:
        msg = load_sample()
        url = extract_livetrack_link_from_message(msg)
        self.assertIsNotNone(url)
        assert url is not None
        self.assertIn("livetrack.garmin.com/session/", url.lower())

    def test_state_store_dedup(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            state = StateStore(Path(tmp_dir) / "state.json")
            self.assertFalse(state.seen("id-1"))
            state.add("id-1")
            self.assertTrue(state.seen("id-1"))

    def test_config_parses_multiple_chat_ids_and_aliases(self) -> None:
        env = {
            "IMAP_USER": "user@example.com",
            "IMAP_APP_PASSWORD": "app-password",
            "TELEGRAM_BOT_TOKEN": "12345:token",
            "TELEGRAM_CHAT_IDS": "-814365864,-1001440633951,7748310522",
            "TELEGRAM_RECIPIENT_ALIASES": "-814365864=sniperimp_monkeys,-1001440633951=family,7748310522=ana",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        self.assertEqual(config.telegram_chat_ids, ["-814365864", "-1001440633951", "7748310522"])
        self.assertEqual(config.telegram_recipient_aliases["7748310522"], "ana")

    def test_config_falls_back_to_legacy_single_chat_id(self) -> None:
        env = {
            "IMAP_USER": "user@example.com",
            "IMAP_APP_PASSWORD": "app-password",
            "TELEGRAM_BOT_TOKEN": "12345:token",
            "TELEGRAM_CHAT_IDS": "",
            "TELEGRAM_CHAT_ID": "123456789",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        self.assertEqual(config.telegram_chat_ids, ["123456789"])

    def test_broadcast_sends_to_all_recipients(self) -> None:
        import tempfile

        msg = load_sample()
        config = Config(
            imap_host="imap.gmail.com",
            imap_port=993,
            imap_user="user@example.com",
            imap_password="app-password",
            telegram_bot_token="12345:token",
            telegram_chat_ids=["-814365864", "-1001440633951", "7748310522"],
            telegram_recipient_aliases={"7748310522": "ana"},
            poll_seconds=30,
            state_path=Path("/tmp/unused-state.json"),
            log_level="INFO",
        )
        sent_to: list[str] = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = StateStore(Path(tmp_dir) / "state.json")
            with patch("livetrack_watcher.fetch_message_ids", return_value=["1"]):
                with patch("livetrack_watcher.fetch_message", return_value=msg):
                    with patch("livetrack_watcher.post_to_telegram") as mocked_send:
                        mocked_send.side_effect = lambda _token, chat_id, _text: sent_to.append(chat_id)
                        count = process_unseen_messages(object(), config, state)  # type: ignore[arg-type]
        self.assertEqual(count, 1)
        self.assertEqual(sent_to, ["-814365864", "-1001440633951", "7748310522"])


if __name__ == "__main__":
    unittest.main()
