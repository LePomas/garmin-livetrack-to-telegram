import email
import email.policy
import json
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


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


def test_extract_livetrack_link_skips_image_url(watcher_module):
    # Arrange
    raw = (
        b"From: Garmin <noreply@garmin.com>\n"
        b"Subject: LiveTrack\n"
        b"Content-Type: text/plain; charset=utf-8\n"
        b"\n"
        b"https://livetrack.garmin.com/banner.png\n"
        b"https://connect.garmin.com/livetrack/invite/abc\n"
    )
    message = email.message_from_bytes(raw, policy=email.policy.default)

    # Act
    link = watcher_module.extract_livetrack_link_from_message(message)

    # Assert
    assert link == "https://connect.garmin.com/livetrack/invite/abc"


def test_extract_livetrack_link_reads_html_multipart(watcher_module):
    # Arrange
    raw = (
        b"From: Garmin <noreply@garmin.com>\n"
        b"Subject: LiveTrack\n"
        b"MIME-Version: 1.0\n"
        b"Content-Type: multipart/alternative; boundary=part\n"
        b"\n"
        b"--part\n"
        b"Content-Type: text/plain; charset=utf-8\n"
        b"\n"
        b"No link here\n"
        b"--part\n"
        b"Content-Type: text/html; charset=utf-8\n"
        b"\n"
        b"<a href=\"https://livetrack.garmin.com/session/html123\">Track</a>\n"
        b"--part--\n"
    )
    message = email.message_from_bytes(raw, policy=email.policy.default)

    # Act
    link = watcher_module.extract_livetrack_link_from_message(message)

    # Assert
    assert link == "https://livetrack.garmin.com/session/html123"


def test_extract_livetrack_link_prefers_livetrack_garmin_url(watcher_module):
    # Arrange
    raw = (
        b"From: Garmin <noreply@garmin.com>\n"
        b"Subject: LiveTrack\n"
        b"Content-Type: text/plain; charset=utf-8\n"
        b"\n"
        b"https://connect.garmin.com/livetrack/invite/abc\n"
        b"https://livetrack.garmin.com/invite/def\n"
    )
    message = email.message_from_bytes(raw, policy=email.policy.default)

    # Act
    link = watcher_module.extract_livetrack_link_from_message(message)

    # Assert
    assert link == "https://livetrack.garmin.com/invite/def"


def test_decode_part_payload_falls_back_for_unknown_charset(watcher_module):
    # Arrange
    raw = (
        b"Content-Type: text/plain; charset=unknown-charset\n"
        b"Content-Transfer-Encoding: base64\n"
        b"\n"
        b"aGVsbG8=\n"
    )
    message = email.message_from_bytes(raw, policy=email.policy.default)

    # Act
    text = watcher_module.decode_part_payload(message)

    # Assert
    assert text == "hello"


def test_decode_part_payload_returns_string_payload(watcher_module):
    # Arrange
    message = email.message_from_string("plain body", policy=email.policy.default)

    # Act
    text = watcher_module.decode_part_payload(message)

    # Assert
    assert text == "plain body"


def test_load_env_file_sets_missing_values_only(watcher_module, tmp_path, monkeypatch):
    # Arrange
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "EXISTING=from-file",
                "NEW_VALUE='from file'",
                "ignored-line",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "from-env")
    monkeypatch.delenv("NEW_VALUE", raising=False)

    # Act
    watcher_module.load_env_file(env_file)

    # Assert
    assert watcher_module.os.environ["EXISTING"] == "from-env"
    assert watcher_module.os.environ["NEW_VALUE"] == "from file"


def test_load_env_file_ignores_missing_file(watcher_module, tmp_path):
    # Arrange
    env_file = tmp_path / "missing.env"

    # Act
    result = watcher_module.load_env_file(env_file)

    # Assert
    assert result is None


def test_config_from_env_uses_defaults_and_minimum_poll_seconds(
    watcher_module, base_env, clear_watcher_env, monkeypatch, tmp_path
):
    # Arrange
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "-1")
    monkeypatch.setenv("POLL_SECONDS", "5")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_IDS", "-99,-98")

    # Act
    config = watcher_module.Config.from_env()

    # Assert
    assert config.imap_host == "imap.gmail.com"
    assert config.imap_port == 993
    assert config.poll_seconds == 10
    assert config.state_path == tmp_path / "state.json"
    assert config.log_level == "DEBUG"
    assert config.telegram_admin_chat_ids == ["-99", "-98"]


def test_require_env_raises_when_value_missing(watcher_module, clear_watcher_env):
    # Arrange
    key = "MISSING_VALUE"

    # Act
    error = None
    try:
        watcher_module.require_env(key)
    except RuntimeError as exc:
        error = exc

    # Assert
    assert str(error) == "Missing required environment variable: MISSING_VALUE"


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


def test_parse_admin_chat_ids_from_env(watcher_module, clear_watcher_env, monkeypatch):
    # Arrange
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_IDS", "-10, -20")

    # Act
    chat_ids = watcher_module.parse_admin_chat_ids()

    # Assert
    assert chat_ids == ["-10", "-20"]


def test_parse_admin_chat_ids_returns_empty_when_unset(watcher_module, clear_watcher_env):
    # Arrange
    admin_chat_ids = None

    # Act
    chat_ids = watcher_module.parse_admin_chat_ids()

    # Assert
    assert admin_chat_ids is None
    assert chat_ids == []


def test_parse_chat_aliases_ignores_invalid_entries(watcher_module, clear_watcher_env, monkeypatch):
    # Arrange
    monkeypatch.setenv("TELEGRAM_RECIPIENT_ALIASES", "-1=team,bad_entry,-2=")

    # Act
    aliases = watcher_module.parse_chat_aliases()

    # Assert
    assert aliases == {"-1": "team"}


def test_parse_chat_aliases_returns_empty_when_unset(watcher_module, clear_watcher_env):
    # Arrange
    aliases_env = None

    # Act
    aliases = watcher_module.parse_chat_aliases()

    # Assert
    assert aliases_env is None
    assert aliases == {}


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


def test_post_to_telegram_raises_on_non_ok_response(watcher_module):
    # Arrange
    response = Mock()
    response.read.return_value = b'{"ok":false}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    # Act
    error = None
    with patch.object(watcher_module.urllib.request, "urlopen", return_value=response):
        try:
            watcher_module.post_to_telegram("token", "-1", "hello")
        except RuntimeError as exc:
            error = exc

    # Assert
    assert str(error) == "Telegram API returned non-ok response"


def test_fetch_telegram_updates_reads_result_and_offset(watcher_module):
    # Arrange
    response = Mock()
    response.read.return_value = b'{"ok":true,"result":[{"update_id":7}]}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    # Act
    with patch.object(watcher_module.urllib.request, "urlopen", return_value=response):
        updates = watcher_module.fetch_telegram_updates("token", 4)
        request_url = watcher_module.urllib.request.urlopen.call_args[0][0].full_url

    # Assert
    assert updates == [{"update_id": 7}]
    assert "offset=4" in request_url


def test_fetch_telegram_updates_raises_on_non_ok_response(watcher_module):
    # Arrange
    response = Mock()
    response.read.return_value = b'{"ok":false}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    # Act
    error = None
    with patch.object(watcher_module.urllib.request, "urlopen", return_value=response):
        try:
            watcher_module.fetch_telegram_updates("token", None)
        except RuntimeError as exc:
            error = exc

    # Assert
    assert str(error) == "Telegram getUpdates returned non-ok response"


def test_parse_telegram_command_accepts_bot_suffix(watcher_module):
    # Arrange
    text = "/request@GarminBot please"

    # Act
    command = watcher_module.parse_telegram_command(text)

    # Assert
    assert command == "/request"


def test_parse_telegram_command_ignores_regular_text(watcher_module):
    # Arrange
    text = "disable"

    # Act
    command = watcher_module.parse_telegram_command(text)

    # Assert
    assert command is None


def test_state_store_loads_and_trims_existing_state(watcher_module, tmp_path):
    # Arrange
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"processed_message_ids": ["1", "2", "3"]}),
        encoding="utf-8",
    )

    # Act
    state = watcher_module.StateStore(state_path, max_entries=2)

    # Assert
    assert state.message_ids == ["2", "3"]


def test_state_store_loads_disabled_chats_and_update_offset(watcher_module, tmp_path):
    # Arrange
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "processed_message_ids": ["1"],
                "disabled_chat_ids": ["-1", 2],
                "pending_subscription_requests": [
                    {
                        "chat_id": "-3",
                        "chat_label": "runner",
                        "requested_at": "2026-05-18T20:00:00-07:00",
                    }
                ],
                "telegram_update_offset": 9,
            }
        ),
        encoding="utf-8",
    )

    # Act
    state = watcher_module.StateStore(state_path)

    # Assert
    assert state.disabled_chat_ids == ["-1", "2"]
    assert state.pending_subscription_requests == [
        {
            "chat_id": "-3",
            "chat_label": "runner",
            "requested_at": "2026-05-18T20:00:00-07:00",
        }
    ]
    assert state.telegram_update_offset == 9


def test_state_store_ignores_unreadable_json(watcher_module, tmp_path):
    # Arrange
    state_path = tmp_path / "state.json"
    state_path.write_text("{not-json", encoding="utf-8")

    # Act
    state = watcher_module.StateStore(state_path)

    # Assert
    assert state.message_ids == []


def test_state_store_disable_enable_and_update_offset_persist(watcher_module, tmp_path):
    # Arrange
    state_path = tmp_path / "state.json"
    state = watcher_module.StateStore(state_path)

    # Act
    state.disable_chat("-1")
    state.set_telegram_update_offset(12)
    state.enable_chat("-1")
    reloaded = watcher_module.StateStore(state_path)

    # Assert
    assert reloaded.disabled_chat_ids == []
    assert reloaded.telegram_update_offset == 12


def test_state_store_add_pending_subscription_request_persists(watcher_module, tmp_path):
    # Arrange
    state_path = tmp_path / "state.json"
    state = watcher_module.StateStore(state_path)
    requested_at = datetime(2026, 5, 18, 20, 30)

    # Act
    created = state.add_pending_subscription_request("-2", "runner", requested_at)
    reloaded = watcher_module.StateStore(state_path)

    # Assert
    assert created is True
    assert reloaded.pending_subscription_requests == [
        {
            "chat_id": "-2",
            "chat_label": "runner",
            "requested_at": "2026-05-18T20:30:00",
        }
    ]


def test_state_store_add_pending_subscription_request_ignores_duplicate(
    watcher_module, tmp_path
):
    # Arrange
    state = watcher_module.StateStore(tmp_path / "state.json")
    requested_at = datetime(2026, 5, 18, 20, 30)
    state.add_pending_subscription_request("-2", "runner", requested_at)

    # Act
    created = state.add_pending_subscription_request("-2", "runner again", requested_at)

    # Assert
    assert created is False
    assert len(state.pending_subscription_requests) == 1


def test_state_store_add_ignores_duplicate_message_id(watcher_module, tmp_path):
    # Arrange
    state = watcher_module.StateStore(tmp_path / "state.json")
    state.add("message-1")

    # Act
    state.add("message-1")

    # Assert
    assert state.message_ids == ["message-1"]


def test_process_telegram_commands_disables_configured_chat(watcher_module, tmp_path):
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
    updates = [{"update_id": 5, "message": {"text": "/disable", "chat": {"id": -1}}}]
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        with patch.object(
            watcher_module,
            "post_to_telegram",
            side_effect=lambda _t, c, _m: sent_to.append(c),
        ):
            watcher_module.process_telegram_commands(config, state)

    # Assert
    assert sent_to == ["-1"]
    assert state.disabled_chat_ids == ["-1"]
    assert state.telegram_update_offset == 6


def test_process_telegram_commands_enables_configured_chat(watcher_module, tmp_path):
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
    state.disable_chat("-1")
    updates = [{"update_id": 6, "message": {"text": "/enable@GarminBot", "chat": {"id": -1}}}]
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        with patch.object(
            watcher_module,
            "post_to_telegram",
            side_effect=lambda _t, c, _m: sent_to.append(c),
        ):
            watcher_module.process_telegram_commands(config, state)

    # Assert
    assert sent_to == ["-1"]
    assert state.disabled_chat_ids == []


def test_process_telegram_commands_ignores_unknown_chat(watcher_module, tmp_path):
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
    updates = [{"update_id": 7, "message": {"text": "/disable", "chat": {"id": -2}}}]

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        watcher_module.process_telegram_commands(config, state)

    # Assert
    assert state.disabled_chat_ids == []


def test_process_telegram_commands_ignores_non_command_message(watcher_module, tmp_path):
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
    updates = [{"update_id": 8, "message": {"text": "hello", "chat": {"id": -1}}}]

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        watcher_module.process_telegram_commands(config, state)

    # Assert
    assert state.disabled_chat_ids == []


def test_process_telegram_commands_records_request_and_notifies_admins_once(
    watcher_module, tmp_path
):
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
        telegram_admin_chat_ids=["-99"],
    )
    state = watcher_module.StateStore(tmp_path / "state.json")
    updates = [
        {
            "update_id": 9,
            "message": {
                "text": "/request",
                "chat": {"id": -2, "first_name": "Runner"},
            },
        }
    ]
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        with patch.object(
            watcher_module,
            "post_to_telegram",
            side_effect=lambda _t, c, _m: sent_to.append(c),
        ):
            watcher_module.process_telegram_commands(config, state)

    # Assert
    assert sent_to == ["-2", "-99"]
    assert state.pending_subscription_requests[0]["chat_id"] == "-2"
    assert state.pending_subscription_requests[0]["chat_label"] == "Runner"


def test_process_telegram_commands_duplicate_request_does_not_notify_admins(
    watcher_module, tmp_path
):
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
        telegram_admin_chat_ids=["-99"],
    )
    state = watcher_module.StateStore(tmp_path / "state.json")
    state.add_pending_subscription_request("-2", "Runner", datetime(2026, 5, 18, 20, 30))
    updates = [{"update_id": 10, "message": {"text": "/request", "chat": {"id": -2}}}]
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        with patch.object(
            watcher_module,
            "post_to_telegram",
            side_effect=lambda _t, c, _m: sent_to.append(c),
        ):
            watcher_module.process_telegram_commands(config, state)

    # Assert
    assert sent_to == ["-2"]
    assert len(state.pending_subscription_requests) == 1


def test_process_telegram_commands_configured_request_replies_without_pending(
    watcher_module, tmp_path
):
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
        telegram_admin_chat_ids=["-99"],
    )
    state = watcher_module.StateStore(tmp_path / "state.json")
    updates = [{"update_id": 11, "message": {"text": "/request", "chat": {"id": -1}}}]
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        with patch.object(
            watcher_module,
            "post_to_telegram",
            side_effect=lambda _t, c, _m: sent_to.append(c),
        ):
            watcher_module.process_telegram_commands(config, state)

    # Assert
    assert sent_to == ["-1"]
    assert state.pending_subscription_requests == []


def test_process_telegram_commands_request_without_admins_records_and_replies(
    watcher_module, tmp_path
):
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
    updates = [{"update_id": 12, "message": {"text": "/request@GarminBot", "chat": {"id": -2}}}]
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_telegram_updates", return_value=updates):
        with patch.object(
            watcher_module,
            "post_to_telegram",
            side_effect=lambda _t, c, _m: sent_to.append(c),
        ):
            watcher_module.process_telegram_commands(config, state)

    # Assert
    assert sent_to == ["-2"]
    assert state.pending_subscription_requests[0]["chat_id"] == "-2"


def test_fetch_message_ids_returns_empty_on_search_failure(watcher_module):
    # Arrange
    conn = Mock()
    conn.search.return_value = ("NO", [])

    # Act
    message_ids = watcher_module.fetch_message_ids(conn)

    # Assert
    assert message_ids == []


def test_fetch_message_ids_decodes_search_results(watcher_module):
    # Arrange
    conn = Mock()
    conn.search.return_value = ("OK", [b"1 2 3"])

    # Act
    message_ids = watcher_module.fetch_message_ids(conn)

    # Assert
    assert message_ids == ["1", "2", "3"]


def test_fetch_message_returns_none_when_fetch_fails(watcher_module):
    # Arrange
    conn = Mock()
    conn.fetch.return_value = ("NO", [])

    # Act
    message = watcher_module.fetch_message(conn, "1")

    # Assert
    assert message is None


def test_fetch_message_parses_rfc822_tuple(watcher_module):
    # Arrange
    conn = Mock()
    conn.fetch.return_value = (
        "OK",
        [(b"1 (RFC822 {12}", b"From: Garmin <noreply@garmin.com>\n\nBody")],
    )

    # Act
    message = watcher_module.fetch_message(conn, "1")

    # Assert
    assert message["From"] == "Garmin <noreply@garmin.com>"


def test_fetch_message_returns_none_without_rfc822_bytes(watcher_module):
    # Arrange
    conn = Mock()
    conn.fetch.return_value = ("OK", [b"FLAGS (\\Seen)"])

    # Act
    message = watcher_module.fetch_message(conn, "1")

    # Assert
    assert message is None


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


def test_process_unseen_messages_skips_disabled_recipient(watcher_module, sample_message, tmp_path):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="app-password",
        telegram_bot_token="12345:token",
        telegram_chat_ids=["-1", "-2"],
        telegram_recipient_aliases={},
        poll_seconds=30,
        state_path=tmp_path / "state.json",
        log_level="INFO",
    )
    state = watcher_module.StateStore(tmp_path / "state.json")
    state.disable_chat("-1")
    sent_to = []

    # Act
    with patch.object(watcher_module, "fetch_message_ids", return_value=["1"]):
        with patch.object(watcher_module, "fetch_message", return_value=sample_message):
            with patch.object(watcher_module, "post_to_telegram", side_effect=lambda _t, c, _m: sent_to.append(c)):
                watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert sent_to == ["-2"]


def test_process_unseen_messages_marks_seen_when_all_recipients_disabled(
    watcher_module, sample_message, tmp_path
):
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
    state.disable_chat("-1")

    # Act
    with patch.object(watcher_module, "fetch_message_ids", return_value=["1"]):
        with patch.object(watcher_module, "fetch_message", return_value=sample_message):
            with patch.object(watcher_module, "post_to_telegram") as post_to_telegram:
                sent_count = watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert sent_count == 0
    assert state.seen("<test-message-id>") is True
    post_to_telegram.assert_not_called()


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


def test_process_unseen_messages_skips_missing_message(watcher_module, tmp_path):
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
        with patch.object(watcher_module, "fetch_message", return_value=None):
            sent_count = watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert sent_count == 0


def test_process_unseen_messages_marks_non_garmin_message_seen(watcher_module, tmp_path):
    # Arrange
    raw = (
        b"From: Example <sender@example.com>\n"
        b"Subject: Hello\n"
        b"Message-ID: <non-garmin>\n"
        b"\n"
        b"Body\n"
    )
    message = email.message_from_bytes(raw, policy=email.policy.default)
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
        with patch.object(watcher_module, "fetch_message", return_value=message):
            sent_count = watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert sent_count == 0
    assert state.seen("<non-garmin>") is True


def test_process_unseen_messages_marks_garmin_without_link_seen(watcher_module, tmp_path):
    # Arrange
    raw = (
        b"From: Garmin <noreply@garmin.com>\n"
        b"Subject: LiveTrack\n"
        b"Message-ID: <no-link>\n"
        b"\n"
        b"No URL here\n"
    )
    message = email.message_from_bytes(raw, policy=email.policy.default)
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
        with patch.object(watcher_module, "fetch_message", return_value=message):
            sent_count = watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert sent_count == 0
    assert state.seen("<no-link>") is True


def test_process_unseen_messages_skips_already_seen_message(watcher_module, sample_message, tmp_path):
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
    state.add("<test-message-id>")

    # Act
    with patch.object(watcher_module, "fetch_message_ids", return_value=["1"]):
        with patch.object(watcher_module, "fetch_message", return_value=sample_message):
            with patch.object(watcher_module, "post_to_telegram") as post_to_telegram:
                sent_count = watcher_module.process_unseen_messages(Mock(), config, state)

    # Assert
    assert sent_count == 0
    post_to_telegram.assert_not_called()


def test_connect_imap_logs_in_and_selects_inbox(watcher_module):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.example.com",
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
    conn = Mock()
    conn.select.return_value = ("OK", [])

    # Act
    with patch.object(watcher_module.imaplib, "IMAP4_SSL", return_value=conn) as imap_ssl:
        result = watcher_module.connect_imap(config)

    # Assert
    assert result is conn
    imap_ssl.assert_called_once_with("imap.example.com", 993, timeout=20)
    conn.login.assert_called_once_with("user@example.com", "app-password")
    conn.select.assert_called_once_with("INBOX")


def test_connect_imap_raises_when_inbox_select_fails(watcher_module):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.example.com",
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
    conn = Mock()
    conn.select.return_value = ("NO", [])

    # Act
    error = None
    with patch.object(watcher_module.imaplib, "IMAP4_SSL", return_value=conn):
        try:
            watcher_module.connect_imap(config)
        except RuntimeError as exc:
            error = exc

    # Assert
    assert str(error) == "Unable to select INBOX"


def test_run_loop_stops_without_noop_after_poll_sleep(watcher_module, tmp_path):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.example.com",
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
    class DummyConn:
        def __init__(self):
            self.noop_calls = 0
            self.logout_calls = 0

        def noop(self):
            self.noop_calls += 1

        def logout(self):
            self.logout_calls += 1

    conn = DummyConn()

    async def run_once():
        stop_event = asyncio.Event()

        async def stop_after_sleep(_stop_event, _seconds):
            stop_event.set()

        async def direct_to_thread(func, /, *args, **kwargs):
            return func(*args, **kwargs)

        with patch.object(
            watcher_module.asyncio, "to_thread", new=direct_to_thread
        ):
            with patch.object(watcher_module, "connect_imap_async", new=AsyncMock(return_value=conn)):
                with patch.object(
                    watcher_module, "process_telegram_commands_async", new=AsyncMock(return_value=None)
                ):
                    with patch.object(
                        watcher_module, "process_unseen_messages_async", new=AsyncMock(return_value=0)
                    ):
                        with patch.object(
                            watcher_module, "wait_for_poll_interval", new=stop_after_sleep
                        ):
                            await watcher_module.run_loop_async(
                                config, stop_event=stop_event, install_signals=False
                            )

    # Act
    asyncio.run(run_once())

    # Assert
    assert conn.noop_calls == 0
    assert conn.logout_calls == 1


def test_run_loop_reconnects_after_noop_failure(watcher_module, tmp_path):
    # Arrange
    config = watcher_module.Config(
        imap_host="imap.example.com",
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

    class DummyConn:
        def __init__(self, fail_noop=False):
            self.fail_noop = fail_noop
            self.noop_calls = 0
            self.logout_calls = 0

        def noop(self):
            self.noop_calls += 1
            if self.fail_noop:
                raise watcher_module.imaplib.IMAP4.error("noop failed")

        def logout(self):
            self.logout_calls += 1

    first_conn = DummyConn(fail_noop=True)
    second_conn = DummyConn()

    async def run_until_reconnect():
        stop_event = asyncio.Event()
        sleep_seconds = []

        async def stop_on_second_poll_sleep(_stop_event, seconds):
            sleep_seconds.append(seconds)
            if sleep_seconds == [30, 15, 30]:
                stop_event.set()

        async def direct_to_thread(func, /, *args, **kwargs):
            return func(*args, **kwargs)

        with patch.object(watcher_module.asyncio, "to_thread", new=direct_to_thread):
            with patch.object(
                watcher_module,
                "connect_imap_async",
                new=AsyncMock(side_effect=[first_conn, second_conn]),
            ) as connect_imap_async:
                with patch.object(
                    watcher_module,
                    "process_telegram_commands_async",
                    new=AsyncMock(return_value=None),
                ):
                    with patch.object(
                        watcher_module,
                        "process_unseen_messages_async",
                        new=AsyncMock(return_value=0),
                    ):
                        with patch.object(
                            watcher_module,
                            "wait_for_poll_interval",
                            new=stop_on_second_poll_sleep,
                        ):
                            await watcher_module.run_loop_async(
                                config, stop_event=stop_event, install_signals=False
                            )

        return connect_imap_async.await_count, sleep_seconds

    # Act
    connect_count, sleep_seconds = asyncio.run(run_until_reconnect())

    # Assert
    assert connect_count == 2
    assert sleep_seconds == [30, 15, 30]
    assert first_conn.noop_calls == 1
    assert first_conn.logout_calls == 1
    assert second_conn.noop_calls == 0
    assert second_conn.logout_calls == 1


def test_parse_args_reads_once_flag(watcher_module, monkeypatch):
    # Arrange
    monkeypatch.setattr(sys, "argv", ["livetrack_watcher.py", "--once"])

    # Act
    args = watcher_module.parse_args()

    # Assert
    assert args.once is True


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
            with patch.object(
                watcher_module, "connect_imap_async", new=AsyncMock(return_value=Mock())
            ):
                with patch.object(
                    watcher_module, "process_telegram_commands_async", new=AsyncMock(return_value=None)
                ):
                    with patch.object(
                        watcher_module, "process_unseen_messages_async", new=AsyncMock(return_value=0)
                    ):
                        with patch.object(
                            watcher_module, "logout_imap_async", new=AsyncMock()
                        ):
                            result = asyncio.run(watcher_module.main_async())

    # Assert
    assert result == 0
