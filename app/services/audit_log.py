"""Append-only file-backed audit log for operator actions.

Stores the most recent MAX_ENTRIES actions. Older entries are dropped
when the log is trimmed on write. All reads return newest-first.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

_STORE_PATH = os.environ.get("AUDIT_LOG_FILE", "/tmp/audit_log.json")
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


def log_action(
    action: str,
    target: str,
    user: str = "admin",
    details: dict[str, Any] | None = None,
) -> None:
    """Append one audit entry. Silently swallows I/O errors so a log failure
    never breaks the operator's intended action."""
    entry = {
        "ts": _now_iso(),
        "action": action,
        "target": target,
        "user": user,
        "details": details or {},
    }
    try:
        entries = _load()
        entries.append(entry)
        _save(entries)
    except Exception:
        pass


def list_entries(limit: int = 100) -> list[dict]:
    """Return up to *limit* most-recent entries, newest first."""
    entries = _load()
    return list(reversed(entries))[:limit]


def clear() -> None:
    _save([])
