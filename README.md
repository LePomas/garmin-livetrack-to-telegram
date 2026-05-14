# Garmin LiveTrack Watcher

Broadcast Garmin LiveTrack email alerts to Telegram recipients.

## 30-Second Orientation
- Core runtime code: `scripts/livetrack_watcher.py`
- Test suite: `tests/scripts/test_livetrack_watcher.py`
- Shared pytest fixtures: `tests/conftest.py`
- Systemd unit source in repo: `garmin-livetrack-watcher.service`
- Runtime env file (local only): `.env`
- Runtime dedupe state (local only): `state/livetrack_state.json`

## Quick Start
1. Run tests:
```bash
./.venv-tests/bin/pytest -q
```
2. Restart service after file changes:
```bash
sudo systemctl restart garmin-livetrack-watcher.service
```
3. Check health:
```bash
sudo systemctl status garmin-livetrack-watcher.service --no-pager
sudo journalctl -u garmin-livetrack-watcher.service -n 80 --no-pager
```

## Repo Map
- `scripts/livetrack_watcher.py`: IMAP polling, Garmin detection, Telegram delivery, message formatting, dedupe state.
- `tests/scripts/test_livetrack_watcher.py`: isolated unit tests with mocks.
- `tests/conftest.py`: reusable fixtures (sample message, env helpers, module loader).
- `garmin-livetrack-watcher.service`: systemd unit template for this project.
- `.env.example`: config template.

## Runtime Flow (Narrow Dependency Map)
1. Connect to IMAP (`connect_imap`).
2. Search unseen messages (`fetch_message_ids`).
3. Load message + detect Garmin LiveTrack (`fetch_message`, `is_garmin_livetrack`).
4. Extract track URL (`extract_livetrack_link_from_message`).
5. Build Telegram text (`build_telegram_message`, `escape_markdown_v2`).
6. Broadcast to all recipients (`post_to_telegram`).
7. Persist processed Message-ID (`StateStore`) to prevent duplicates.

## Configuration
Primary variables:
- `TELEGRAM_BOT_TOKEN`: bot token.
- `TELEGRAM_CHAT_IDS`: comma-separated recipient chat IDs (broadcast target list).
- `TELEGRAM_RECIPIENT_ALIASES`: optional `chat_id=alias` pairs for logs.
- `IMAP_USER`, `IMAP_APP_PASSWORD`: mailbox credentials.

Additional variables:
- `IMAP_HOST` (default `imap.gmail.com`)
- `IMAP_PORT` (default `993`)
- `POLL_SECONDS` (minimum `10`, default `30`)
- `LOG_LEVEL` (default `INFO`)
- `STATE_PATH` (optional override)

Compatibility:
- If `TELEGRAM_CHAT_IDS` is missing/empty, watcher falls back to legacy `TELEGRAM_CHAT_ID`.

## Common Tasks
Run tests:
```bash
./.venv-tests/bin/pytest -q
```

Restart service (required after project file edits):
```bash
sudo systemctl restart garmin-livetrack-watcher.service
```

Install/update unit file from repo copy:
```bash
sudo install -m 0644 garmin-livetrack-watcher.service /etc/systemd/system/garmin-livetrack-watcher.service
sudo systemctl daemon-reload
sudo systemctl enable --now garmin-livetrack-watcher.service
```

## Troubleshooting
`service active but no alerts`:
- verify `.env` token/chat IDs and IMAP credentials
- check logs for IMAP auth or Telegram API failures

`duplicate alerts`:
- verify `state/livetrack_state.json` is writable
- avoid clearing state file unless intentional

`tests fail locally`:
- ensure `pytest` exists in `./.venv-tests`
- run exactly: `./.venv-tests/bin/pytest -q`

## Rollback (Git)
1. `sudo systemctl stop garmin-livetrack-watcher.service`
2. `git checkout <known-good-commit-or-tag>`
3. `sudo install -m 0644 garmin-livetrack-watcher.service /etc/systemd/system/garmin-livetrack-watcher.service`
4. `sudo systemctl daemon-reload`
5. `sudo systemctl enable --now garmin-livetrack-watcher.service`
