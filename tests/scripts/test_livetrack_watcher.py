from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch


def test_is_garmin_livetrack_true(watcher_module, sample_message):
    # Arrange
    message = sample_message

    # Act
    result = watcher_module.is_garmin_livetrack(message)

    # Assert
    assert result is True


def test_extract_livetrack_link_returns_session_url(watcher_module, sample_message):
    # Arrange
    message = sample_message

    # Act
    link = watcher_module.extract_livetrack_link_from_message(message)

    # Assert
    assert link == "https://livetrack.garmin.com/session/sample-session-123"


def test_parse_chat_ids_from_telegram_chat_ids(watcher_module, base_env, clear_watcher_env, monkeypatch):
    # Arrange
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "-1,-2,3")

    # Act
    chat_ids = watcher_module.parse_chat_ids()

    # Assert
    assert chat_ids == ["-1", "-2", "3"]


def test_parse_chat_ids_fallback_legacy(watcher_module, base_env, clear_watcher_env, monkeypatch):
    # Arrange
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")

    # Act
    chat_ids = watcher_module.parse_chat_ids()

    # Assert
    assert chat_ids == ["999"]


def test_parse_chat_aliases_ignores_invalid_entries(watcher_module, clear_watcher_env, monkeypatch):
    # Arrange
    monkeypatch.setenv("TELEGRAM_RECIPIENT_ALIASES", "-1=team,bad_entry,-2=")

    # Act
    aliases = watcher_module.parse_chat_aliases()

    # Assert
    assert aliases == {"-1": "team"}


def test_escape_markdown_v2_escapes_special_chars(watcher_module):
    # Arrange
    text = "a_b[c]!"

    # Act
    escaped = watcher_module.escape_markdown_v2(text)

    # Assert
    assert escaped == "a\\_b\\[c\\]\\!"


def test_build_telegram_message_contains_bold_subject(watcher_module):
    # Arrange
    dt = datetime(2026, 5, 12, 16, 50)

    # Act
    message = watcher_module.build_telegram_message(
        link="https://livetrack.garmin.com/session/x",
        subject="Garmin LiveTrack Update",
        received_at=dt,
    )

    # Assert
    assert "🚴 *Garmin LiveTrack Update* 🏃" in message


def test_build_telegram_message_contains_date_time_line(watcher_module):
    # Arrange
    dt = datetime(2026, 5, 12, 16, 50)

    # Act
    message = watcher_module.build_telegram_message(
        link="https://livetrack.garmin.com/session/x",
        subject="Garmin LiveTrack Update",
        received_at=dt,
    )

    # Assert
    assert "📅 *Date:* 12/05/2026 \\| 🕒 *Time:* 16:50" in message


def test_post_to_telegram_uses_markdown_v2(watcher_module):
    # Arrange
    token = "123:abc"
    chat_id = "-1"
    text = "hello"
    response = Mock()
    response.read.return_value = b'{"ok":true}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    # Act
    with patch.object(watcher_module.urllib.request, "urlopen", return_value=response):
        watcher_module.post_to_telegram(token, chat_id, text)
        parse_mode = watcher_module.urllib.request.urlopen.call_args[0][0].data.decode("utf-8")

    # Assert
    assert "parse_mode=MarkdownV2" in parse_mode


def test_process_unseen_messages_broadcasts_all_recipients(watcher_module, sample_message, tmp_path):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="app-password",
        telegram_bot_token="12345:token",
        telegram_chat_ids=["-1", "-2", "3"],
        telegram_recipient_aliases={},
        poll_seconds=30,
        state_path=tmp_path / "state.json",
        log_level="INFO",
    )
    state = watcher_module.StateStore(tmp_path / "state.json")
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_message_ids", return_value=["1"]):
        with patch.object(watcher_module, "fetch_message", return_value=sample_message):
            with patch.object(watcher_module, "post_to_telegram", side_effect=lambda _t, c, _m: sent_to.append(c)):
                watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert sent_to == ["-1", "-2", "3"]


def test_process_unseen_messages_marks_seen_message_in_state(watcher_module, sample_message, tmp_path):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="app-password",
        telegram_bot_token="12345:token",
        telegram_chat_ids=["-1"],
        telegram_recipient_aliases={},
        poll_seconds=30,
        state_path=tmp_path / "state.json",
        log_level="INFO",
    )
    state = watcher_module.StateStore(tmp_path / "state.json")

    # Act
    with patch.object(watcher_module, "fetch_message_ids", return_value=["1"]):
        with patch.object(watcher_module, "fetch_message", return_value=sample_message):
            with patch.object(watcher_module, "post_to_telegram", return_value=None):
                watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert state.seen("<test-message-id>") is True


def test_process_unseen_messages_raises_on_partial_delivery_failure(watcher_module, sample_message, tmp_path):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="app-password",
        telegram_bot_token="12345:token",
        telegram_chat_ids=["-1", "-2"],
        telegram_recipient_aliases={"-2": "backup"},
        poll_seconds=30,
        state_path=tmp_path / "state.json",
        log_level="INFO",
    )
    state = watcher_module.StateStore(tmp_path / "state.json")

    # Act
    with patch.object(watcher_module, "fetch_message_ids", return_value=["1"]):
        with patch.object(watcher_module, "fetch_message", return_value=sample_message):
            with patch.object(
                watcher_module,
                "post_to_telegram",
                side_effect=[None, RuntimeError("failed")],
            ):
                with patch("builtins.print"):
                    error = None
                    try:
                        watcher_module.process_unseen_messages(Mock(), config, state)
                    except RuntimeError as exc:
                        error = exc

    # Assert
    assert isinstance(error, RuntimeError)


def test_main_once_mode_returns_zero(watcher_module):
    # Arrange
    args = Mock()
    args.once = True
    config = watcher_module.Config(
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="app-password",
        telegram_bot_token="12345:token",
        telegram_chat_ids=["-1"],
        telegram_recipient_aliases={},
        poll_seconds=30,
        state_path=Path("/tmp/state.json"),
        log_level="INFO",
    )

    # Act
    with patch.object(watcher_module, "parse_args", return_value=args):
        with patch.object(watcher_module.Config, "from_env", return_value=config):
            with patch.object(watcher_module, "connect_imap") as connect_imap:
                conn = Mock()
                connect_imap.return_value = conn
                with patch.object(watcher_module, "process_unseen_messages", return_value=0):
                    result = watcher_module.main()

    # Assert
    assert result == 0
