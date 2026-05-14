import email
import email.policy
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def watcher_module():
    scripts_path = Path(__file__).resolve().parents[1] / "scripts"
    scripts_path_str = str(scripts_path)
    if scripts_path_str not in sys.path:
        sys.path.insert(0, scripts_path_str)
    import livetrack_watcher

    return livetrack_watcher


@pytest.fixture
def sample_message():
    raw = (
        b"From: Garmin <noreply@garmin.com>\n"
        b"Subject: Garmin LiveTrack Update\n"
        b"Message-ID: <test-message-id>\n"
        b"Content-Type: text/plain; charset=utf-8\n"
        b"\n"
        b"Track here: https://livetrack.garmin.com/session/sample-session-123\n"
    )
    return email.message_from_bytes(raw, policy=email.policy.default)


@pytest.fixture
def base_env():
    return {
        "IMAP_USER": "user@example.com",
        "IMAP_APP_PASSWORD": "app-password",
        "TELEGRAM_BOT_TOKEN": "12345:token",
    }


@pytest.fixture
def clear_watcher_env(monkeypatch):
    keys = [
        "IMAP_HOST",
        "IMAP_PORT",
        "IMAP_USER",
        "IMAP_APP_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_CHAT_IDS",
        "TELEGRAM_RECIPIENT_ALIASES",
        "POLL_SECONDS",
        "STATE_PATH",
        "LOG_LEVEL",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    return os.environ
