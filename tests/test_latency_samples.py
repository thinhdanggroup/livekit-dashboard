"""Tests for the in-memory latency ring-buffer sample store.

No persistence: this module is a deliberate in-memory-only accumulator
(matching the module-level-dict pattern in app/services/cache.py). Each
test calls ls._reset_for_tests() first since module state otherwise
leaks between tests and these assertions are exact.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import app.services.latency_samples as ls
from app.services.livekit import LiveKitClient


def test_percentiles_none_when_no_samples():
    ls._reset_for_tests()
    assert ls.percentiles("api_list_rooms") is None


def test_percentiles_single_sample_all_equal():
    ls._reset_for_tests()
    ls.record("api_list_rooms", 42.0)
    result = ls.percentiles("api_list_rooms")
    assert result == {"p50": 42.0, "p90": 42.0, "p99": 42.0, "count": 1}


def test_percentiles_multiple_samples():
    ls._reset_for_tests()
    for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        ls.record("api_list_rooms", float(v))
    result = ls.percentiles("api_list_rooms")
    assert result["count"] == 10
    assert 40 <= result["p50"] <= 60
    assert result["p99"] >= result["p90"] >= result["p50"]


def test_percentiles_respects_window(monkeypatch):
    ls._reset_for_tests()
    ls.record("api_list_rooms", 999.0, ts=1000.0)   # old sample
    ls.record("api_list_rooms", 10.0, ts=1700.0)    # recent sample
    monkeypatch.setattr(ls.time, "time", lambda: 1700.0)
    result = ls.percentiles("api_list_rooms", window_seconds=60)
    assert result["count"] == 1
    assert result["p50"] == 10.0


def test_ring_buffer_bounded(monkeypatch):
    ls._reset_for_tests()
    monkeypatch.setattr(ls, "MAX_SAMPLES", 3)
    for v in range(5):
        ls.record("api_list_rooms", float(v))
    result = ls.percentiles("api_list_rooms")
    assert result["count"] == 3


def test_list_op_types_only_includes_recorded():
    ls._reset_for_tests()
    ls.record("api_list_rooms", 1.0)
    assert ls.list_op_types() == ["api_list_rooms"]


def test_recent_samples_newest_first_and_limited():
    ls._reset_for_tests()
    ls.record("api_list_rooms", 1.0, ts=100.0)
    ls.record("api_list_rooms", 2.0, ts=200.0)
    ls.record("api_list_rooms", 3.0, ts=300.0)
    result = ls.recent_samples("api_list_rooms", limit=2)
    assert result == [(300.0, 3.0), (200.0, 2.0)]


def test_recent_samples_respects_window(monkeypatch):
    ls._reset_for_tests()
    ls.record("api_list_rooms", 1.0, ts=100.0)
    ls.record("api_list_rooms", 2.0, ts=1700.0)
    monkeypatch.setattr(ls.time, "time", lambda: 1700.0)
    result = ls.recent_samples("api_list_rooms", window_seconds=60)
    assert result == [(1700.0, 2.0)]


def test_recent_samples_empty_for_unknown_op_type():
    ls._reset_for_tests()
    assert ls.recent_samples("unknown_op") == []


# ---------------------------------------------------------------------------
# Integration: real instrumentation points in app.services.livekit.LiveKitClient
# ---------------------------------------------------------------------------


async def test_list_rooms_records_latency_sample():
    """list_rooms measures latency in seconds internally; the recorded sample
    must be converted to milliseconds (latency * 1000) before being stored."""
    ls._reset_for_tests()
    client = LiveKitClient()
    mock_api = MagicMock()
    mock_api.room.list_rooms = AsyncMock(return_value=MagicMock(rooms=[]))

    with patch.object(client, "_get_api", new=AsyncMock(return_value=mock_api)):
        await client.list_rooms()

    result = ls.percentiles("api_list_rooms")
    assert result is not None
    assert result["count"] == 1


async def test_connect_to_room_for_stats_records_latency_sample():
    """connect_to_room_for_stats already computes latency in milliseconds
    ((perf_counter delta) * 1000); it must be recorded as-is, with no extra
    multiplication, on both the success and error paths."""
    ls._reset_for_tests()
    client = LiveKitClient()

    mock_room = MagicMock()
    mock_room.connect = AsyncMock(return_value=None)
    mock_room.isconnected = MagicMock(return_value=True)
    mock_room.get_rtc_stats = AsyncMock(return_value=MagicMock())
    mock_room.disconnect = AsyncMock(return_value=None)

    with patch("app.services.livekit.rtc.Room", return_value=mock_room), patch(
        "app.services.livekit.asyncio.sleep", new=AsyncMock(return_value=None)
    ):
        await client.connect_to_room_for_stats("test-room")

    result = ls.percentiles("rtc_connect")
    assert result is not None
    assert result["count"] == 1


async def test_connect_to_room_for_stats_records_latency_sample_on_error():
    """The error path (room.connect raises) must still record a sample."""
    ls._reset_for_tests()
    client = LiveKitClient()

    mock_room = MagicMock()
    mock_room.connect = AsyncMock(side_effect=RuntimeError("connect failed"))
    mock_room.disconnect = AsyncMock(return_value=None)

    with patch("app.services.livekit.rtc.Room", return_value=mock_room):
        stats, latency, error_msg = await client.connect_to_room_for_stats("test-room")

    assert error_msg == "connect failed"
    result = ls.percentiles("rtc_connect")
    assert result is not None
    assert result["count"] == 1
