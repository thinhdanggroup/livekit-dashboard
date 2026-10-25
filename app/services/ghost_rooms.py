"""File-backed tracker for rooms that disappeared between polls ("ghost" rooms).

Each call to record_poll() receives the currently-live rooms, diffs them
against the previously-seen live set, and records any room that vanished as
a ghost with a closed_at timestamp. Ghosts expire after TTL_MINUTES.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_STORE_PATH = os.environ.get("GHOST_ROOMS_FILE", "/tmp/ghost_rooms.json")
TTL_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> dict[str, Any]:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"live": {}, "ghosts": {}}


def _save(state: dict[str, Any]) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _minutes_since(closed_at: str, now: datetime) -> int:
    return int((now - datetime.fromisoformat(closed_at)).total_seconds() // 60)


def record_poll(live_rooms: list[dict]) -> list[dict]:
    """Record one poll of live rooms and return the surviving ghost entries,
    newest-closed first.

    Fails open: any error while reading/updating the on-disk state (e.g. a
    corrupted store file missing an expected key) is logged and swallowed so
    a tracking failure never breaks the /rooms page that calls this.
    """
    try:
        now = _now()
        now_iso = now.isoformat(timespec="seconds")
        state = _load()
        previous_live: dict[str, Any] = state.get("live", {})
        ghosts: dict[str, Any] = state.get("ghosts", {})

        live_snapshots = {room["name"]: room for room in live_rooms}

        # A room that is live again is never also a ghost.
        for name in live_snapshots:
            ghosts.pop(name, None)

        # Rooms seen live last poll but absent now have closed.
        for name, snapshot in previous_live.items():
            if name not in live_snapshots:
                ghosts[name] = {**snapshot, "closed_at": now_iso}

        state["live"] = live_snapshots

        # Expire ghosts that have been closed for at least TTL_MINUTES.
        ghosts = {
            name: ghost
            for name, ghost in ghosts.items()
            if _minutes_since(ghost["closed_at"], now) < TTL_MINUTES
        }
        state["ghosts"] = ghosts
        _save(state)

        entries = []
        for name, ghost in ghosts.items():
            entries.append({
                "name": name,
                "max_participants": ghost["max_participants"],
                "creation_time": ghost["creation_time"],
                "metadata": ghost["metadata"],
                "closed_at": ghost["closed_at"],
                "closed_minutes_ago": _minutes_since(ghost["closed_at"], now),
            })
        entries.sort(key=lambda e: datetime.fromisoformat(e["closed_at"]), reverse=True)
        return entries
    except Exception:
        logger.warning("ghost_rooms.record_poll failed; skipping ghost tracking for this poll", exc_info=True)
        return []
