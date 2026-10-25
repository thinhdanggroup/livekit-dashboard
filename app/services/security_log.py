"""Append-only file-backed log of failed login attempts.

Stores the most recent MAX_ENTRIES failures. Older entries are dropped
when the log is trimmed on write. All reads return newest-first.
"""

import json
import os
from collections import Counter
from datetime import datetime, timezone

_STORE_PATH = os.environ.get("SECURITY_LOG_FILE", "/tmp/security_log.json")
MAX_ENTRIES = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[dict]:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(entries: list[dict]) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(entries[-MAX_ENTRIES:], f, indent=2)


def log_failed_login(ip: str, username: str) -> None:
    """Append one failed-login entry. Silently swallows I/O errors so a log
    failure never breaks the auth rejection it records."""
    entry = {"ts": _now_iso(), "ip": ip, "username": username}
    try:
        entries = _load()
        entries.append(entry)
        _save(entries)
    except Exception:
        pass


def list_failed_logins(limit: int = 100) -> list[dict]:
    """Return up to *limit* most-recent failed logins, newest first."""
    entries = _load()
    return list(reversed(entries))[:limit]


def count_by_ip(limit: int = 500) -> dict[str, int]:
    """Count failed attempts per IP over the most recent *limit* entries,
    sorted by count descending."""
    recent = _load()[-limit:]
    counts = Counter(entry["ip"] for entry in recent)
    return dict(counts.most_common())
