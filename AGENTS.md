# AGENTS Guide

This file defines how coding agents should work in this repo to avoid long discovery flows and context overload.

## Mission
- Keep the Garmin LiveTrack watcher reliable.
- Preserve low-resource operation for hosts like Raspberry Pi Zero 2 W.
- Make minimal, targeted changes.
- Validate quickly and restart the service after project file modifications.

## Guardrails
- Do not scan the whole repo by default.
- Do not edit `.env` unless explicitly requested.
- Do not track runtime artifacts (`state/livetrack_state.json`, `.env.bak-*`).
- Keep changes narrow: prefer one subsystem per commit.
- Keep runtime code dependency-free unless a dependency removes clear operational risk.

## Runtime Design Principles
- Keep IMAP access and state-file writes serialized; do not parallelize operations on the same IMAP connection.
- Keep Telegram delivery sequential for small recipient lists. Add concurrency only if measured latency or recipient count justifies the extra failure handling.
- If using `asyncio`, use it for lifecycle control, stop-aware sleeping, and wrapping blocking network calls.
- Avoid half-converted async wrappers that are not on the runtime path.
- Prefer bounded timeouts and retry sleeps over tight reconnect loops.

## Fast Discovery Protocol (Use This Order)
1. `README.md` (task context and commands)
2. `scripts/livetrack_watcher.py` (runtime behavior)
3. `tests/scripts/test_livetrack_watcher.py` (expected behavior)
4. `tests/conftest.py` (fixture setup and isolation)
5. `garmin-livetrack-watcher.service` (only if service/runtime path issue)

Default command sequence:
```bash
git status --short --branch
ls -la
sed -n '1,260p' scripts/livetrack_watcher.py
sed -n '1,260p' tests/scripts/test_livetrack_watcher.py
```

## Context Budget Rules
- Read only files needed for the current task.
- If more than 3 files are opened, summarize current findings before opening more.
- If more than 120 lines are needed from a file, read targeted slices instead of full file dumps.
- Stop exploration once you can name exact edit points.

## Dependency Map (Operational)
- Inbound: IMAP (`connect_imap`, `fetch_message_ids`, `fetch_message`)
- Filter/parser: `is_garmin_livetrack`, `extract_livetrack_link_from_message`
- Formatting: `build_telegram_message`, `escape_markdown_v2`
- Outbound: `post_to_telegram` (Telegram API)
- Dedupe persistence: `StateStore` + `state/livetrack_state.json`

## Change Workflow
1. Confirm target function(s) and minimal edit scope.
2. Implement changes.
3. Run tests:
```bash
./.venv-tests/bin/pytest -q
```
4. Restart service (mandatory after project file edits):
```bash
sudo systemctl restart garmin-livetrack-watcher.service
sudo systemctl status garmin-livetrack-watcher.service --no-pager
```
5. Report: files changed, test result, service status.

## Testing Standards
- Use pytest under `tests/` mirroring repo layout.
- Use fixtures for shared setup.
- Mock cross-boundary dependencies (`IMAP`, `Telegram/network`, time/signal side effects when applicable).
- Keep one behavioral assertion per test.
- Include explicit `# Arrange`, `# Act`, `# Assert` comments in tests.

## Done Checklist
- Change is minimal and scoped.
- Tests pass locally.
- Service restarted and active.
- No runtime artifacts accidentally staged.
- Output/report is concise and actionable.
