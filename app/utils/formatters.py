"""Display helpers registered as Jinja2 filters in app/main.py.

Templates can use:
  {{ seconds | duration }}       → "3m 20s"
  {{ value   | pct }}            → "98.5%"
  {{ status  | status_color }}   → "success"  (Bootstrap color name)
  {{ count   | numformat }}      → "1.5K"
"""

from __future__ import annotations

import math


def format_duration(seconds: float | int | None) -> str:
    """Human-readable duration from seconds.

    Returns '—' for None, negative, or non-numeric input.
    """
    try:
        s = int(math.floor(float(seconds)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"

    if s < 0:
        return "—"
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s" if s else f"{m}m"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m" if m else f"{h}h"
    d, h = divmod(h, 24)
    return f"{d}d {h}h" if h else f"{d}d"


def format_pct(value: float | int | None, decimals: int = 1) -> str:
    """Percentage string with fixed decimal places.

    Returns '—' for None or non-numeric input.
    """
    try:
        return f"{float(value):.{decimals}f}%"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"


_STATUS_COLORS: dict[str, str] = {
    "active": "success",
    "started": "success",
    "running": "success",
    "connected": "success",
    "online": "success",
    "ok": "success",
    "idle": "secondary",
    "waiting": "secondary",
    "inactive": "secondary",
    "stopped": "danger",
    "failed": "danger",
    "error": "danger",
    "disconnected": "danger",
    "offline": "danger",
    "pending": "warning",
    "starting": "warning",
    "reconnecting": "warning",
}


def status_color(status: str | None, default: str = "secondary") -> str:
    """Bootstrap contextual color name for a status string.

    Unknown statuses return *default* ('secondary').
    """
    if not status:
        return default
    return _STATUS_COLORS.get(str(status).lower().strip(), default)


def format_number(value: float | int | None) -> str:
    """Compact number with K/M suffix for large values.

    Returns '—' for None or non-numeric input.
    """
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"

    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n)) if n == int(n) else f"{n:.1f}"
