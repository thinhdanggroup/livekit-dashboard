"""Shared query-parameter filter state.

Parse common filter params (search, sort, time range, live-refresh) from
a FastAPI Request into a single typed FilterState object.  All list views
and dashboard routes should call parse_filters(request) rather than
reading request.query_params directly — this keeps validation and defaults
in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from fastapi import Request


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


PRESET_MINUTES: dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "24h": 24 * 60,
    "7d": 7 * 24 * 60,
}

_MIN_REFRESH = 5
_MAX_REFRESH = 300
_DEFAULT_REFRESH = 30


@dataclass
class FilterState:
    """Parsed, validated filter state derived from request query params."""

    q: str = ""
    sort: SortOrder = SortOrder.DESC
    sort_by: str = "created_at"
    time_range: str = ""
    live_refresh: bool = False
    refresh_interval: int = _DEFAULT_REFRESH

    @property
    def time_range_minutes(self) -> Optional[int]:
        """Minutes for the selected preset, or None when no preset is active."""
        return PRESET_MINUTES.get(self.time_range)

    def as_query_params(self) -> dict[str, str]:
        """Serialize non-default values back to a query-string dict.

        Useful for building HTMX hx-get URLs and pagination links that
        preserve the current filter state.
        """
        params: dict[str, str] = {}
        if self.q:
            params["q"] = self.q
        if self.sort != SortOrder.DESC:
            params["sort"] = self.sort.value
        if self.sort_by != "created_at":
            params["sort_by"] = self.sort_by
        if self.time_range:
            params["time_range"] = self.time_range
        if self.live_refresh:
            params["live_refresh"] = "1"
            params["refresh_interval"] = str(self.refresh_interval)
        return params


def parse_filters(request: Request) -> FilterState:
    """Build a FilterState from a FastAPI request's query parameters.

    All params are optional; missing or invalid values fall back to their
    documented defaults so callers never need to handle None.
    """
    params = request.query_params

    q = (params.get("q", "") or params.get("search", "")).strip()

    raw_sort = params.get("sort", "").lower()
    sort = SortOrder.ASC if raw_sort == "asc" else SortOrder.DESC

    sort_by = params.get("sort_by", "created_at").strip() or "created_at"

    raw_tr = params.get("time_range", "")
    time_range = raw_tr if raw_tr in PRESET_MINUTES else ""

    live_refresh = params.get("live_refresh", "") in ("1", "true", "yes")

    try:
        refresh_interval = max(
            _MIN_REFRESH,
            min(_MAX_REFRESH, int(params.get("refresh_interval", str(_DEFAULT_REFRESH)))),
        )
    except (ValueError, TypeError):
        refresh_interval = _DEFAULT_REFRESH

    return FilterState(
        q=q,
        sort=sort,
        sort_by=sort_by,
        time_range=time_range,
        live_refresh=live_refresh,
        refresh_interval=refresh_interval,
    )
