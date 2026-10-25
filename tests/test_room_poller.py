"""Tests for the background room lifecycle poller."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.ghost_rooms as gr
import app.services.room_history as rh
import app.services.room_poller as rp


@pytest.fixture(autouse=True)
def _reset_poller_state():
    """Every test starts from a clean in-memory last-known-state dict."""
    rp._reset_for_tests()
    yield
    rp._reset_for_tests()


def _room(name, num_participants=0, max_participants=10, creation_time=1, metadata=""):
    return SimpleNamespace(
        name=name,
        num_participants=num_participants,
        max_participants=max_participants,
        creation_time=creation_time,
        metadata=metadata,
    )


def _participant(identity, tracks=None):
    return SimpleNamespace(identity=identity, tracks=tracks or [])


def _track(sid, muted=False):
    return SimpleNamespace(sid=sid, muted=muted)


async def test_poll_once_records_room_created_on_first_sighting(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(gr, "_STORE_PATH", str(tmp_path / "g.json"))

    lk = MagicMock()
    lk.list_rooms = AsyncMock(return_value=([_room("r1")], 0.01))
    lk.list_participants = AsyncMock(return_value=[])

    await rp.poll_once(lk)

    assert any(e["kind"] == "room_created" for e in rh.get_history("r1"))


async def test_poll_once_records_join_across_two_ticks(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(gr, "_STORE_PATH", str(tmp_path / "g.json"))

    lk = MagicMock()

    # First tick: room with no participants.
    lk.list_rooms = AsyncMock(return_value=([_room("r1")], 0.01))
    lk.list_participants = AsyncMock(return_value=[])
    await rp.poll_once(lk)

    # Second tick: same room now has participant "alice".
    lk.list_rooms = AsyncMock(return_value=([_room("r1", num_participants=1)], 0.01))
    lk.list_participants = AsyncMock(return_value=[_participant("alice")])
    await rp.poll_once(lk)

    history = rh.get_history("r1")
    assert any(e["kind"] == "participant_joined" and e["identity"] == "alice" for e in history)


async def test_poll_once_continues_after_one_room_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(gr, "_STORE_PATH", str(tmp_path / "g.json"))

    lk = MagicMock()
    lk.list_rooms = AsyncMock(return_value=([_room("bad"), _room("good")], 0.01))

    async def _list_participants(room_name):
        if room_name == "bad":
            raise RuntimeError("room vanished mid-tick")
        return []

    lk.list_participants = AsyncMock(side_effect=_list_participants)

    await rp.poll_once(lk)

    assert rh.get_history("bad") == []
    assert any(e["kind"] == "room_created" for e in rh.get_history("good"))


async def test_poll_once_detects_track_mute(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(gr, "_STORE_PATH", str(tmp_path / "g.json"))

    lk = MagicMock()
    lk.list_rooms = AsyncMock(return_value=([_room("r1")], 0.01))
    lk.list_participants = AsyncMock(
        return_value=[_participant("alice", tracks=[_track("t1", muted=False)])]
    )
    await rp.poll_once(lk)

    lk.list_participants = AsyncMock(
        return_value=[_participant("alice", tracks=[_track("t1", muted=True)])]
    )
    await rp.poll_once(lk)

    history = rh.get_history("r1")
    assert any(e["kind"] == "track_muted" and e["identity"] == "alice" for e in history)


async def test_poll_once_treats_reappearing_room_as_fresh_without_ended_event(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(gr, "_STORE_PATH", str(tmp_path / "g.json"))

    lk = MagicMock()

    # Tick 1: room r1 is live.
    lk.list_rooms = AsyncMock(return_value=([_room("r1")], 0.01))
    lk.list_participants = AsyncMock(return_value=[])
    await rp.poll_once(lk)

    # Tick 2: room r1 disappears.
    lk.list_rooms = AsyncMock(return_value=([], 0.01))
    await rp.poll_once(lk)

    assert "r1" not in rp._last_known
    assert not any(e["kind"] == "room_ended" for e in rh.get_history("r1"))

    # Tick 3: room r1 reappears -- treated as freshly seen, so room_created fires again.
    lk.list_rooms = AsyncMock(return_value=([_room("r1")], 0.01))
    lk.list_participants = AsyncMock(return_value=[])
    await rp.poll_once(lk)

    created_events = [e for e in rh.get_history("r1") if e["kind"] == "room_created"]
    assert len(created_events) == 2


async def test_run_poller_loop_survives_list_rooms_failure(monkeypatch):
    """run_poller_loop must swallow poll_once failures and keep ticking."""
    calls = []

    async def _fake_poll_once(lk):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(rp, "poll_once", _fake_poll_once)

    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio_cancelled()

    import asyncio

    def asyncio_cancelled():
        return asyncio.CancelledError()

    monkeypatch.setattr(rp.asyncio, "sleep", _fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await rp.run_poller_loop(interval_seconds=0)

    assert len(calls) == 2
