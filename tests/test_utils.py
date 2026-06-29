"""Tests for app.utils.filters and app.utils.formatters"""
from unittest.mock import MagicMock

import pytest

from app.utils.filters import PRESET_MINUTES, FilterState, SortOrder, parse_filters
from app.utils.formatters import format_duration, format_number, format_pct, status_color


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req(params: dict) -> MagicMock:
    req = MagicMock()
    req.query_params = params
    return req


# ---------------------------------------------------------------------------
# parse_filters / FilterState
# ---------------------------------------------------------------------------

def test_parse_filters_defaults():
    f = parse_filters(_req({}))
    assert f.q == ""
    assert f.sort == SortOrder.DESC
    assert f.sort_by == "created_at"
    assert f.time_range == ""
    assert f.live_refresh is False
    assert f.refresh_interval == 30


def test_parse_filters_strips_search_query():
    f = parse_filters(_req({"q": "  my room  "}))
    assert f.q == "my room"


def test_parse_filters_sort_asc():
    assert parse_filters(_req({"sort": "asc"})).sort == SortOrder.ASC


def test_parse_filters_sort_invalid_falls_back_to_desc():
    assert parse_filters(_req({"sort": "random"})).sort == SortOrder.DESC


def test_parse_filters_sort_by_custom():
    f = parse_filters(_req({"sort_by": "name"}))
    assert f.sort_by == "name"


def test_parse_filters_sort_by_blank_falls_back():
    f = parse_filters(_req({"sort_by": "   "}))
    assert f.sort_by == "created_at"


@pytest.mark.parametrize("preset", list(PRESET_MINUTES))
def test_parse_filters_valid_time_ranges(preset):
    f = parse_filters(_req({"time_range": preset}))
    assert f.time_range == preset
    assert f.time_range_minutes == PRESET_MINUTES[preset]


def test_parse_filters_invalid_time_range_ignored():
    f = parse_filters(_req({"time_range": "99y"}))
    assert f.time_range == ""
    assert f.time_range_minutes is None


@pytest.mark.parametrize("val", ["1", "true", "yes"])
def test_parse_filters_live_refresh_truthy(val):
    assert parse_filters(_req({"live_refresh": val})).live_refresh is True


@pytest.mark.parametrize("val", ["0", "false", "no", ""])
def test_parse_filters_live_refresh_falsy(val):
    assert parse_filters(_req({"live_refresh": val})).live_refresh is False


def test_parse_filters_refresh_interval_clamped_low():
    f = parse_filters(_req({"live_refresh": "1", "refresh_interval": "2"}))
    assert f.refresh_interval == 5  # min is 5


def test_parse_filters_refresh_interval_clamped_high():
    f = parse_filters(_req({"live_refresh": "1", "refresh_interval": "9999"}))
    assert f.refresh_interval == 300  # max is 300


def test_parse_filters_refresh_interval_invalid():
    f = parse_filters(_req({"live_refresh": "1", "refresh_interval": "bad"}))
    assert f.refresh_interval == 30  # default


def test_filter_state_as_query_params_empty():
    assert FilterState().as_query_params() == {}


def test_filter_state_as_query_params_populated():
    f = FilterState(q="test", sort=SortOrder.ASC, time_range="1h", live_refresh=True)
    p = f.as_query_params()
    assert p["q"] == "test"
    assert p["sort"] == "asc"
    assert p["time_range"] == "1h"
    assert p["live_refresh"] == "1"
    assert p["refresh_interval"] == "30"


def test_filter_state_as_query_params_omits_defaults():
    f = FilterState()
    p = f.as_query_params()
    assert "sort" not in p
    assert "sort_by" not in p
    assert "live_refresh" not in p


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("secs,expected", [
    (0, "0s"),
    (1, "1s"),
    (59, "59s"),
    (60, "1m"),
    (61, "1m 1s"),
    (90, "1m 30s"),
    (3600, "1h"),
    (3660, "1h 1m"),
    (3661, "1h 1m"),
    (86400, "1d"),
    (86400 + 3600, "1d 1h"),
    (86400 + 3600 * 3, "1d 3h"),
])
def test_format_duration_valid(secs, expected):
    assert format_duration(secs) == expected


def test_format_duration_float_input():
    assert format_duration(90.9) == "1m 30s"


@pytest.mark.parametrize("bad", [None, "bad", -1, -60])
def test_format_duration_invalid(bad):
    assert format_duration(bad) == "—"


# ---------------------------------------------------------------------------
# format_pct
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("val,expected", [
    (0, "0.0%"),
    (100, "100.0%"),
    (98.5, "98.5%"),
    (33.333, "33.3%"),
])
def test_format_pct_valid(val, expected):
    assert format_pct(val) == expected


def test_format_pct_decimals_param():
    assert format_pct(98.567, decimals=2) == "98.57%"


@pytest.mark.parametrize("bad", [None, "bad"])
def test_format_pct_invalid(bad):
    assert format_pct(bad) == "—"


# ---------------------------------------------------------------------------
# status_color
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,color", [
    ("active", "success"),
    ("ACTIVE", "success"),
    ("  running  ", "success"),
    ("failed", "danger"),
    ("error", "danger"),
    ("disconnected", "danger"),
    ("pending", "warning"),
    ("starting", "warning"),
    ("idle", "secondary"),
    ("waiting", "secondary"),
    ("unknown_xyz", "secondary"),
])
def test_status_color_known(status, color):
    assert status_color(status) == color


@pytest.mark.parametrize("bad", [None, ""])
def test_status_color_empty(bad):
    assert status_color(bad) == "secondary"


def test_status_color_custom_default():
    assert status_color("", default="info") == "info"


# ---------------------------------------------------------------------------
# format_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,expected", [
    (0, "0"),
    (999, "999"),
    (1000, "1.0K"),
    (1500, "1.5K"),
    (999_999, "1000.0K"),
    (1_000_000, "1.0M"),
    (2_500_000, "2.5M"),
])
def test_format_number_valid(n, expected):
    assert format_number(n) == expected


@pytest.mark.parametrize("bad", [None, "bad"])
def test_format_number_invalid(bad):
    assert format_number(bad) == "—"
