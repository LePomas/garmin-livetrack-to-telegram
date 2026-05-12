#!/usr/bin/env python3
"""Watch a mailbox for Garmin LiveTrack emails and forward links to Telegram."""

from __future__ import annotations

import argparse
import email
import email.policy
import imaplib
import json
import logging
import os
import re
import signal
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path

LOG = logging.getLogger("livetrack_watcher")

GARMIN_SENDER = "noreply@garmin.com"
SUBJECT_HINT = "livetrack"
URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
LIVETRACK_HINTS = ("livetrack", "garmin.com")
DISALLOWED_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "livetrack_state.json"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


@dataclass
class Config:
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    telegram_bot_token: str
    telegram_chat_ids: list[str]
    telegram_recipient_aliases: dict[str, str]
    poll_seconds: int
    state_path: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        skill_dir = Path(__file__).resolve().parent.parent
        load_env_file(skill_dir / ".env")
        return cls(
            imap_host=os.environ.get("IMAP_HOST", "imap.gmail.com"),
            imap_port=int(os.environ.get("IMAP_PORT", "993")),
            imap_user=require_env("IMAP_USER"),
            imap_password=require_env("IMAP_APP_PASSWORD"),
            telegram_bot_token=require_env("TELEGRAM_BOT_TOKEN"),
            telegram_chat_ids=parse_chat_ids(),
            telegram_recipient_aliases=parse_chat_aliases(),
            poll_seconds=max(10, int(os.environ.get("POLL_SECONDS", "30"))),
            state_path=Path(os.environ.get("STATE_PATH", str(DEFAULT_STATE_PATH))).expanduser(),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


def require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


def parse_chat_ids() -> list[str]:
    raw = os.environ.get("TELEGRAM_CHAT_IDS", "").strip()
    if raw:
        chat_ids = [item.strip() for item in raw.split(",") if item.strip()]
        if chat_ids:
            return chat_ids
    return [require_env("TELEGRAM_CHAT_ID")]


def parse_chat_aliases() -> dict[str, str]:
    raw = os.environ.get("TELEGRAM_RECIPIENT_ALIASES", "").strip()
    if not raw:
        return {}
    aliases: dict[str, str] = {}
    for item in raw.split(","):
        entry = item.strip()
        if not entry or "=" not in entry:
            continue
        chat_id, alias = entry.split("=", 1)
        chat_id = chat_id.strip()
        alias = alias.strip()
        if chat_id and alias:
            aliases[chat_id] = alias
    return aliases


class StateStore:
    def __init__(self, path: Path, max_entries: int = 2000):
        self.path = path
        self.max_entries = max_entries
        self.message_ids: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data.get("processed_message_ids", [])
            if isinstance(items, list):
                self.message_ids = [str(x) for x in items][-self.max_entries :]
        except (json.JSONDecodeError, OSError):
            LOG.warning("State file unreadable; starting fresh: %s", self.path)

    def seen(self, message_id: str) -> bool:
        return message_id in self.message_ids

    def add(self, message_id: str) -> None:
        if message_id in self.message_ids:
            return
        self.message_ids.append(message_id)
        self.message_ids = self.message_ids[-self.max_entries :]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"processed_message_ids": self.message_ids}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_garmin_livetrack(msg: Message) -> bool:
    sender = (msg.get("From") or "").lower()
    subject = (msg.get("Subject") or "").lower()
    return GARMIN_SENDER in sender and SUBJECT_HINT in subject


def decode_part_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def extract_livetrack_link_from_message(msg: Message) -> str | None:
    bodies: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in {"text/plain", "text/html"}:
                bodies.append(decode_part_payload(part))
    else:
        bodies.append(decode_part_payload(msg))

    candidates: list[str] = []
    for body in bodies:
        for candidate in URL_PATTERN.findall(body):
            clean = candidate.rstrip(").,;!\"'")
            lower = clean.lower()
            if all(hint in lower for hint in LIVETRACK_HINTS):
                if any(lower.endswith(ext) for ext in DISALLOWED_SUFFIXES):
                    continue
                candidates.append(clean)

    for url in candidates:
        lower = url.lower()
        if "livetrack.garmin.com/session/" in lower:
            return url
    for url in candidates:
        lower = url.lower()
        if "livetrack.garmin.com/" in lower:
            return url
    if candidates:
        return candidates[0]
    return None


def fetch_message_ids(conn: imaplib.IMAP4_SSL) -> list[str]:
    status, data = conn.search(None, "UNSEEN")
    if status != "OK" or not data:
        return []
    return [x for x in data[0].decode("utf-8").split() if x]


def fetch_message(conn: imaplib.IMAP4_SSL, msg_id: str) -> Message | None:
    status, data = conn.fetch(msg_id, "(RFC822)")
    if status != "OK" or not data:
        return None
    raw_bytes = None
    for item in data:
        if isinstance(item, tuple) and len(item) > 1:
            raw_bytes = item[1]
            break
    if not raw_bytes:
        return None
    return email.message_from_bytes(raw_bytes, policy=email.policy.default)


def post_to_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(url=url, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
    if '"ok":true' not in body:
        raise RuntimeError("Telegram API returned non-ok response")


def build_telegram_message(link: str, subject: str, received_at: str) -> str:
    return f"Garmin LiveTrack\n{subject}\n{received_at}\n{link}"


def process_unseen_messages(conn: imaplib.IMAP4_SSL, config: Config, state: StateStore) -> int:
    sent_count = 0
    for msg_id in fetch_message_ids(conn):
        msg = fetch_message(conn, msg_id)
        if msg is None:
            continue
        message_id = (msg.get("Message-ID") or "").strip() or f"imap-{msg_id}"
        if state.seen(message_id):
            continue
        if not is_garmin_livetrack(msg):
            state.add(message_id)
            continue
        link = extract_livetrack_link_from_message(msg)
        if not link:
            LOG.warning("No LiveTrack URL found in message %s", message_id)
            state.add(message_id)
            continue
        subject = (msg.get("Subject") or "Garmin LiveTrack").strip()
        dt = datetime.now(timezone.utc).isoformat()
        text = build_telegram_message(link=link, subject=subject, received_at=dt)
        errors: list[str] = []
        sent_recipients = 0
        for chat_id in config.telegram_chat_ids:
            alias = config.telegram_recipient_aliases.get(chat_id, chat_id)
            try:
                post_to_telegram(config.telegram_bot_token, chat_id, text)
                sent_recipients += 1
                LOG.info("Delivered LiveTrack message %s to %s", message_id, alias)
            except (urllib.error.URLError, RuntimeError, OSError) as exc:
                errors.append(f"{alias}: {exc}")
                LOG.warning("Failed to deliver LiveTrack message %s to %s: %s", message_id, alias, exc)
        if errors:
            raise RuntimeError(
                f"Failed Telegram delivery for message {message_id}; "
                f"sent={sent_recipients}/{len(config.telegram_chat_ids)}; "
                f"errors={'; '.join(errors)}"
            )
        state.add(message_id)
        sent_count += 1
        LOG.info("Forwarded LiveTrack message %s to %d recipients", message_id, sent_recipients)
    return sent_count


def connect_imap(config: Config) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
    conn.login(config.imap_user, config.imap_password)
    status, _ = conn.select("INBOX")
    if status != "OK":
        raise RuntimeError("Unable to select INBOX")
    return conn


def run_loop(config: Config) -> None:
    stop = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    state = StateStore(config.state_path)
    conn: imaplib.IMAP4_SSL | None = None

    while not stop:
        try:
            if conn is None:
                conn = connect_imap(config)
                LOG.info("Connected to IMAP server %s", config.imap_host)
            sent = process_unseen_messages(conn, config, state)
            LOG.debug("Scan complete; forwarded=%d", sent)
            time.sleep(config.poll_seconds)
            conn.noop()
        except (imaplib.IMAP4.error, OSError, urllib.error.URLError, RuntimeError) as exc:
            LOG.warning("Watcher error: %s", exc)
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass
            conn = None
            time.sleep(min(config.poll_seconds, 15))
        except Exception:
            LOG.exception("Unexpected error")
            time.sleep(10)

    if conn is not None:
        try:
            conn.logout()
        except Exception:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward Garmin LiveTrack links from email to Telegram.")
    parser.add_argument("--once", action="store_true", help="Process unseen messages once, then exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Config.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.once:
        conn = connect_imap(config)
        try:
            state = StateStore(config.state_path)
            process_unseen_messages(conn, config, state)
        finally:
            conn.logout()
        return 0

    run_loop(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
