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

        # manually age the file's last event by writing an old ts, then prune
        with open(store_path) as f:
            state = json.load(f)
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=TTL_MINUTES + 1)).isoformat(
            timespec="seconds"
        )
        state["r1"][-1]["ts"] = old_ts
        with open(store_path, "w") as f:
            json.dump(state, f)

        rh.prune_old(datetime.now(timezone.utc))
        assert rh.get_history("r1") == []
