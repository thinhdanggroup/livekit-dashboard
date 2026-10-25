"""Append-only file-backed log of failed login attempts.

Stores the most recent MAX_ENTRIES failures. Older entries are dropped
when the log is trimmed on write. All reads return newest-first.

requires_admin runs synchronously (FastAPI runs sync dependencies in a
threadpool), so concurrent failed-login attempts call log_failed_login
from multiple threads at once -- exactly the brute-force traffic this log
exists to surface. _LOCK serializes the read-modify-write sequence across
threads in this process, and _save's write-to-temp-then-os.replace swap
ensures any reader (including a different request calling
list_failed_logins/count_by_ip) never observes a torn/partial write.
"""

import json
import logging
import os
import threading
from collections import Counter
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_STORE_PATH = os.environ.get("SECURITY_LOG_FILE", "/tmp/security_log.json")
MAX_ENTRIES = 500
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[dict]:
    """Load the raw store contents.

    Mirrors app/services/ip_allowlist.py's _load: a missing file is the
    normal state for a fresh install and is handled silently, while any
    other failure to read or parse the store (a directory at the path,
    permission error, malformed JSON, non-UTF-8 bytes) is logged and
    treated as "no entries yet" rather than propagating and 500ing the
    /settings page that also surfaces this log.
    """
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("security_log store unreadable at %s (%s); treating as empty", _STORE_PATH, exc)
        return []
    if not isinstance(data, list):
        return []
    return data


def _save(entries: list[dict]) -> None:
    """Write entries atomically: write to a temp file in the same directory,
    then os.replace() it into place, so a concurrent reader never sees a
    partially-written file."""
    directory = os.path.dirname(_STORE_PATH) or "."
    tmp_path = os.path.join(directory, f".{os.path.basename(_STORE_PATH)}.tmp-{os.getpid()}-{threading.get_ident()}")
    with open(tmp_path, "w") as f:
        json.dump(entries[-MAX_ENTRIES:], f, indent=2)
    os.replace(tmp_path, _STORE_PATH)


def log_failed_login(ip: str, username: str) -> None:
    """Append one failed-login entry. Silently swallows I/O errors so a log
    failure never breaks the auth rejection it records.

    Holds _LOCK around the full load-append-trim-save sequence to prevent
    the classic read-modify-write race when multiple threads (concurrent
    failed-login attempts via requires_admin) call this at once.
    """
    entry = {"ts": _now_iso(), "ip": ip, "username": username}
    try:
        with _LOCK:
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
