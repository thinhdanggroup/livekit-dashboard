"""Append-only file-backed log of outbound webhook deliveries.

Stores the most recent MAX_ENTRIES deliveries. Older entries are dropped
when the log is trimmed on write. All reads return newest-first.
"""

import json
import os
import uuid
from datetime import datetime, timezone

_STORE_PATH = os.environ.get("WEBHOOK_LOG_FILE", "/tmp/webhook_log.json")
MAX_ENTRIES = 200


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


def log_delivery(
    source: str,
    url: str,
    payload: str,
    status: int | None,
    error: str | None,
) -> str:
    """Append one delivery entry and return its generated id."""
    entry_id = str(uuid.uuid4())[:8]
    entry = {
        "id": entry_id,
        "ts": _now_iso(),
        "source": source,
        "url": url,
        "payload": payload,
        "status": status,
        "error": error,
    }
    entries = _load()
    entries.append(entry)
    _save(entries)
    return entry_id


def list_entries(limit: int = 100) -> list[dict]:
    """Return up to *limit* most-recent entries, newest first."""
    entries = _load()
    return list(reversed(entries))[:limit]


def get_entry(entry_id: str) -> dict | None:
    """Return the entry with the given id, or None if it is not stored."""
    for entry in _load():
        if entry["id"] == entry_id:
            return entry
    return None
