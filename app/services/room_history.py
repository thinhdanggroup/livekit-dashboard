"""File-backed per-room lifecycle event history, plus the pure state-diff
function used to derive those events from successive room-state snapshots.

Shape on disk: {room_name: {"events": [{"ts": iso, "kind": str, "label":
str, "identity": str}, ...], "last_seen": iso}}, events chronological
(oldest first) within each room. "last_seen" tracks the last poller tick
that observed the room as live -- NOT the timestamp of the last event --
because a quiet, live room (no joins/leaves/mutes) can otherwise go
TTL_MINUTES without a single event and have its entire history pruned while
still live. The poller updates last_seen every tick via mark_seen(), whether
or not a diff event fired that tick. Retention is governed by TTL_MINUTES
(imported from ghost_rooms, not redeclared here) so a room's history and its
ghost-row visibility can never drift out of sync: prune_old drops any room
whose last_seen predates that same TTL.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.services.ghost_rooms import TTL_MINUTES

_STORE_PATH = os.environ.get("ROOM_HISTORY_FILE", "/tmp/room_history.json")
MAX_EVENTS_PER_ROOM = 500


def _load() -> dict[str, Any]:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(state: dict[str, Any]) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _minutes_since(ts: str, now: datetime) -> int:
    return int((now - datetime.fromisoformat(ts)).total_seconds() // 60)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_event(room_name: str, kind: str, label: str, identity: str = "") -> None:
    """Append one lifecycle event for room_name, timestamped now.

    Appending an event always implies the room was just observed live, so
    this also bumps last_seen to now (same as mark_seen would)."""
    state = _load()
    entry = state.get(room_name, {"events": [], "last_seen": _now_iso()})
    events = entry.get("events", [])
    events.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "label": label,
            "identity": identity,
        }
    )
    entry["events"] = events[-MAX_EVENTS_PER_ROOM:]
    entry["last_seen"] = _now_iso()
    state[room_name] = entry
    _save(state)


def mark_seen(room_name: str, now: datetime) -> None:
    """Record that room_name was observed live at `now`, without appending
    an event. Called every poller tick for every currently-live room so a
    quiet room's retention window keeps advancing even when nothing
    happens. Creates the room's entry (with empty events) if it doesn't
    exist yet."""
    state = _load()
    entry = state.get(room_name, {"events": []})
    entry["last_seen"] = now.isoformat(timespec="seconds")
    state[room_name] = entry
    _save(state)


def get_history(room_name: str) -> list[dict]:
    """Return room_name's events, chronological (oldest first); [] if the
    room is unknown or its history has already been pruned."""
    state = _load()
    return state.get(room_name, {}).get("events", [])


def prune_old(now: datetime) -> None:
    """Drop any room whose last_seen predates TTL_MINUTES."""
    state = _load()
    state = {
        room_name: entry
        for room_name, entry in state.items()
        if entry.get("last_seen") and _minutes_since(entry["last_seen"], now) < TTL_MINUTES
    }
    _save(state)


def diff_room_state(prev: dict | None, curr: dict) -> tuple[list[dict], dict]:
    """Diff two {"participants": {identity: {"muted_tracks": set[str]}}}
    snapshots and return (events, new_state).

    prev=None means the room has never been seen before: no join/leave
    events are synthesized for its existing participants (they joined
    before this poller started watching), only the raw state is handed
    back as new_state for next time's diff.
    """
    curr_participants: dict[str, Any] = curr.get("participants", {})
    new_state = {
        "participants": {
            identity: {"muted_tracks": set(data.get("muted_tracks", set()))}
            for identity, data in curr_participants.items()
        }
    }

    if prev is None:
        return [], new_state

    prev_participants: dict[str, Any] = prev.get("participants", {})
    events: list[dict] = []

    for identity in curr_participants:
        if identity not in prev_participants:
            events.append(
                {"kind": "participant_joined", "label": f"{identity} joined", "identity": identity}
            )

    for identity in prev_participants:
        if identity not in curr_participants:
            events.append(
                {"kind": "participant_left", "label": f"{identity} left", "identity": identity}
            )

    for identity in curr_participants:
        if identity not in prev_participants:
            continue
        prev_muted = prev_participants[identity].get("muted_tracks", set())
        curr_muted = curr_participants[identity].get("muted_tracks", set())
        for track in curr_muted - prev_muted:
            events.append(
                {
                    "kind": "track_muted",
                    "label": f"{identity} muted {track}",
                    "identity": identity,
                }
            )
        for track in prev_muted - curr_muted:
            events.append(
                {
                    "kind": "track_unmuted",
                    "label": f"{identity} unmuted {track}",
                    "identity": identity,
                }
            )

    return events, new_state
