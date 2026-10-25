"""Tests for the in-memory latency ring-buffer sample store.

No persistence: this module is a deliberate in-memory-only accumulator
(matching the module-level-dict pattern in app/services/cache.py). Each
test calls ls._reset_for_tests() first since module state otherwise
leaks between tests and these assertions are exact.
"""

import app.services.latency_samples as ls


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
