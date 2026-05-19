# Garmin LiveTrack Watcher

Garmin LiveTrack Watcher polls an email inbox for Garmin LiveTrack messages and forwards the LiveTrack link to one or more Telegram chats.

The project is intentionally small: one Python script, a systemd unit example, and unit tests with IMAP and Telegram calls mocked out.

## Features

- Watches unread IMAP messages for Garmin LiveTrack alerts.
- Extracts LiveTrack URLs from plain text or HTML email bodies.
- Sends MarkdownV2-formatted Telegram messages to one or more chat IDs.
- Lets configured Telegram chats pause alerts with `/disable` and resume them with `/enable`.
- Lets unknown Telegram chats request access with `/request`, notifying configured admins.
- Stores processed email `Message-ID` values in a local state file to reduce duplicate alerts.
- Can run once for smoke testing or continuously as a long-running service.

## Requirements

- Python 3.10 or newer.
- An IMAP mailbox that receives Garmin LiveTrack emails.
- Telegram bot token and target chat ID or IDs.
- `systemd` only if you want the included service setup.

The runtime script uses only the Python standard library. `pytest` is needed only for tests.

## Installation

Clone the repo and create a virtual environment:

```bash
git clone https://github.com/your-user/garmin-livetrack-watcher.git
cd garmin-livetrack-watcher
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install ".[test]"
```

Create a local config file:

```bash
cp .env.example .env
```

Edit `.env` with your mailbox and Telegram settings. Do not commit `.env`.

## Configuration

Required variables:

- `TELEGRAM_BOT_TOKEN`: Telegram bot token from BotFather.
- `TELEGRAM_CHAT_IDS`: comma-separated Telegram chat IDs to receive alerts.
- `IMAP_USER`: mailbox username.
- `IMAP_APP_PASSWORD`: mailbox password or app password.

Optional variables:

- `TELEGRAM_ADMIN_CHAT_IDS`: comma-separated Telegram chat IDs that receive `/request` notifications.
- `TELEGRAM_RECIPIENT_ALIASES`: comma-separated `chat_id=alias` pairs used only in logs.
- `TELEGRAM_CHAT_ID`: legacy single-recipient fallback if `TELEGRAM_CHAT_IDS` is unset.
- `IMAP_HOST`: defaults to `imap.gmail.com`.
- `IMAP_PORT`: defaults to `993`.
- `POLL_SECONDS`: polling interval, minimum `10`, default `30`.
- `LOG_LEVEL`: Python logging level, default `INFO`.
- `STATE_PATH`: custom dedupe state path. Defaults to `state/livetrack_state.json`.

For Gmail, enable IMAP and use an app password rather than your account password.

## Usage

Run one scan and exit:

```bash
./.venv/bin/python scripts/livetrack_watcher.py --once
```

Run continuously:

```bash
./.venv/bin/python scripts/livetrack_watcher.py
```

The script loads `.env` from the repository root if it exists. Existing environment variables take precedence because `.env` values are loaded with `setdefault`.

Configured Telegram recipients can send `/disable` to the bot to stop receiving LiveTrack alerts, then `/enable` to resume them. Commands only affect the chat that sent the command, and chats not listed in `TELEGRAM_CHAT_IDS` are ignored.

Unknown Telegram chats can send `/request` to ask for access. The bot replies to the requester, stores one pending request per chat in the state file, and notifies `TELEGRAM_ADMIN_CHAT_IDS` if configured. Approval is manual: add the requested chat ID to `TELEGRAM_CHAT_IDS` in `.env` or deployment config.

## Running As A Service

The repo includes `garmin-livetrack-watcher.service` as a systemd example. It contains local paths and must be edited before installing on another machine.

After adjusting `WorkingDirectory`, `ExecStart`, and `EnvironmentFile`, install it with:

```bash
sudo install -m 0644 garmin-livetrack-watcher.service /etc/systemd/system/garmin-livetrack-watcher.service
sudo systemctl daemon-reload
sudo systemctl enable --now garmin-livetrack-watcher.service
```

Check service health:

```bash
sudo systemctl status garmin-livetrack-watcher.service --no-pager
sudo journalctl -u garmin-livetrack-watcher.service -n 80 --no-pager
```

Restart after project file changes:

```bash
sudo systemctl restart garmin-livetrack-watcher.service
```

## Tests

Run the test suite:

```bash
./.venv/bin/python -m pytest -q
```

Tests are unit-level and mock network boundaries. They do not connect to IMAP or Telegram.

## Troubleshooting

Service is active but no alerts arrive:

- Confirm Garmin emails are arriving unread in the configured inbox.
- Check `.env` values for bot token, chat IDs, and IMAP credentials.
- Inspect logs with `journalctl` for IMAP authentication or Telegram API errors.

Duplicate alerts:

- Confirm the state file path is writable by the service user.
- Avoid deleting `state/livetrack_state.json` unless you intentionally want to reprocess messages.
- The same state file also stores disabled Telegram recipients, pending subscription requests, and the Telegram update offset.

Telegram formatting errors:

- Check logs for Telegram API responses.
- The script sends with MarkdownV2 and escapes message fields before posting.

Tests fail locally:

- Reinstall test dependencies with `./.venv/bin/python -m pip install ".[test]"`.
- Run from the repository root.

## Limitations

- The watcher searches unread messages only.
- Detection is tuned for Garmin sender and LiveTrack subject hints.
- Telegram delivery is best-effort per polling cycle; partial recipient failures raise an error so the message can be retried.
- The project does not include OAuth setup for email providers.

## Security And Privacy

- Never commit `.env`, mailbox credentials, Telegram bot tokens, chat IDs, or state files.
- `.env.example` uses placeholders only.
- `state/livetrack_state.json` may contain email message IDs and is ignored by Git.
- Logs can include recipient aliases and message IDs. Use non-sensitive aliases.

## Runtime

- The watcher now uses `asyncio` for its polling loop and shutdown coordination.
- IMAP and Telegram HTTP calls stay on the standard library and run in worker threads so the deployment footprint stays small.
- Current behavior remains unchanged:
  - `/disable` and `/enable` still apply per chat.
  - `/request` still records one pending request per chat and notifies admins.
  - LiveTrack email forwarding still deduplicates by `Message-ID`.

## License

MIT. See `LICENSE`.
