# Garmin LiveTrack Watcher

Standalone systemd-managed watcher that forwards Garmin LiveTrack emails to Telegram.

## Service
- Unit name: `garmin-livetrack-watcher.service`
- Boot target: `multi-user.target`

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
