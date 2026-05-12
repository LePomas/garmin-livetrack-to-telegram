# Garmin LiveTrack Watcher

Standalone systemd-managed watcher that forwards Garmin LiveTrack emails to Telegram.
Delivery mode is broadcast: each LiveTrack message is sent to every configured recipient.

## Service
- Unit name: `garmin-livetrack-watcher.service`
- Boot target: `multi-user.target`

## Configuration
- Primary recipients variable: `TELEGRAM_CHAT_IDS` (comma-separated chat IDs).
- Optional aliases for logs: `TELEGRAM_RECIPIENT_ALIASES` as `chat_id=alias` pairs.
- Backward compatibility: if `TELEGRAM_CHAT_IDS` is not set, watcher falls back to `TELEGRAM_CHAT_ID`.
- Current known chat IDs:
  - `-814365864` (`sniperimp_monkeys`)
  - `-1001440633951` (`family`)
  - `7748310522` (`ana`, once confirmed from updates)

## Rollback (single-step)
1. `sudo systemctl stop garmin-livetrack-watcher.service`
2. `git checkout <pre-change-tag>`
3. `sudo install -m 0644 garmin-livetrack-watcher.service /etc/systemd/system/garmin-livetrack-watcher.service`
4. `sudo systemctl daemon-reload`
5. `sudo systemctl enable --now garmin-livetrack-watcher.service`

## Notes
- Keep `.env` local to this repo.
- State file is persisted at `state/livetrack_state.json`.

## Migration
- `.env` was copied from the former skill path to this repo.
- `state/livetrack_state.json` was migrated from the former skill state path to preserve dedupe.
