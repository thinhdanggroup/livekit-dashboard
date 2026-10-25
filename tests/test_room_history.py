"""Tests for the room lifecycle history store and the pure diff function."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app.services.room_history as rh
from app.services.ghost_rooms import TTL_MINUTES


# ---------------------------------------------------------------------------
# diff_room_state: pure function, no I/O, hand-constructed state dicts
# ---------------------------------------------------------------------------

def test_diff_first_sighting_produces_no_events():
    events, state = rh.diff_room_state(None, {"participants": {"a": {"muted_tracks": set()}}})
    assert events == []
    assert state == {"participants": {"a": {"muted_tracks": set()}}}


def test_diff_detects_join_and_leave():
    prev = {"participants": {"a": {"muted_tracks": set()}}}
    curr = {"participants": {"b": {"muted_tracks": set()}}}
    events, _ = rh.diff_room_state(prev, curr)
    kinds_identities = {(e["kind"], e["identity"]) for e in events}
    assert ("participant_left", "a") in kinds_identities
    assert ("participant_joined", "b") in kinds_identities


def test_diff_detects_mute_and_unmute():
    prev = {"participants": {"a": {"muted_tracks": set()}}}
    curr = {"participants": {"a": {"muted_tracks": {"track1"}}}}
    events, _ = rh.diff_room_state(prev, curr)
    assert any(e["kind"] == "track_muted" and e["identity"] == "a" for e in events)

    events2, _ = rh.diff_room_state(curr, prev)
    assert any(e["kind"] == "track_unmuted" and e["identity"] == "a" for e in events2)


# ---------------------------------------------------------------------------
# append_event / get_history / prune_old: file-backed store
# ---------------------------------------------------------------------------

def test_append_and_get_history_chronological(tmp_path):
    with patch.object(rh, "_STORE_PATH", str(tmp_path / "h.json")):
        rh.append_event("r1", "room_created", "Room created")
        rh.append_event("r1", "participant_joined", "alice joined", identity="alice")
        history = rh.get_history("r1")
    assert [e["kind"] for e in history] == ["room_created", "participant_joined"]


def test_get_history_unknown_room_empty(tmp_path):
    with patch.object(rh, "_STORE_PATH", str(tmp_path / "h.json")):
        assert rh.get_history("nope") == []


def test_prune_old_drops_stale_rooms(tmp_path):
    store_path = tmp_path / "h.json"
    with patch.object(rh, "_STORE_PATH", str(store_path)):
        rh.append_event("r1", "room_created", "Room created")

        # manually age the room's last_seen (not just its last event) by
        # writing an old ts, then prune
        with open(store_path) as f:
            state = json.load(f)
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=TTL_MINUTES + 1)).isoformat(
            timespec="seconds"
        )
        state["r1"]["events"][-1]["ts"] = old_ts
        state["r1"]["last_seen"] = old_ts
        with open(store_path, "w") as f:
            json.dump(state, f)

        rh.prune_old(datetime.now(timezone.utc))
        assert rh.get_history("r1") == []


# ---------------------------------------------------------------------------
# mark_seen / retention tied to "last observed live", not "last event"
# ---------------------------------------------------------------------------

def test_prune_old_drops_room_with_old_last_seen_even_with_old_event(tmp_path):
    """A room whose last_seen is stale gets pruned, even though it has an
    (also old) event in its history -- last_seen, not the event's own
    timestamp, drives retention."""
    store_path = tmp_path / "h.json"
    with patch.object(rh, "_STORE_PATH", str(store_path)):
        rh.append_event("r1", "room_created", "Room created")

        old_ts = datetime.now(timezone.utc) - timedelta(minutes=TTL_MINUTES + 1)
        with open(store_path) as f:
            state = json.load(f)
        state["r1"]["events"][-1]["ts"] = old_ts.isoformat(timespec="seconds")
        state["r1"]["last_seen"] = old_ts.isoformat(timespec="seconds")
        with open(store_path, "w") as f:
            json.dump(state, f)

        rh.prune_old(datetime.now(timezone.utc))
        assert rh.get_history("r1") == []


def test_prune_old_keeps_quiet_live_room_with_old_last_event_but_recent_mark_seen(tmp_path):
    """Reproduces the original bug report: a room with an old last EVENT
    (room_created + participant_joined, 16+ minutes ago) that has been
    repeatedly mark_seen-ed since (simulating a quiet but still-live room,
    e.g. a quiet 1:1 call) must NOT be pruned -- its history must survive."""
    store_path = tmp_path / "h.json"
    with patch.object(rh, "_STORE_PATH", str(store_path)):
        rh.append_event("r1", "room_created", "Room created")
        rh.append_event("r1", "participant_joined", "alice joined", identity="alice")

        # Age the events themselves by TTL_MINUTES + 1, as the probe did.
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=TTL_MINUTES + 1)).isoformat(
            timespec="seconds"
        )
        with open(store_path) as f:
            state = json.load(f)
        for event in state["r1"]["events"]:
            event["ts"] = old_ts
        with open(store_path, "w") as f:
            json.dump(state, f)

        # But the room has kept being observed live every tick since then,
        # most recently just now.
        rh.mark_seen("r1", datetime.now(timezone.utc))

        rh.prune_old(datetime.now(timezone.utc))

        history = rh.get_history("r1")
        assert [e["kind"] for e in history] == ["room_created", "participant_joined"]


def test_mark_seen_creates_entry_without_events(tmp_path):
    with patch.object(rh, "_STORE_PATH", str(tmp_path / "h.json")):
        rh.mark_seen("r1", datetime.now(timezone.utc))
        assert rh.get_history("r1") == []
        rh.prune_old(datetime.now(timezone.utc))
        assert rh.get_history("r1") == []


def test_get_history_returns_plain_list_not_dict(tmp_path):
    """External contract: get_history always returns a plain list of
    events, never the internal {"events": [...], "last_seen": ...} dict."""
    with patch.object(rh, "_STORE_PATH", str(tmp_path / "h.json")):
        rh.append_event("r1", "room_created", "Room created")
        history = rh.get_history("r1")
        assert isinstance(history, list)
        assert all(isinstance(e, dict) and "kind" in e for e in history)
