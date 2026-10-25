"""In-memory ring-buffer store of per-op-type latency samples.

No persistence: this is a deliberate in-memory-only accumulator, same
tradeoff as the module-level TTL cache in app/services/cache.py. State
lives for the life of the process and resets on restart.

Callers (a later task) record latencies from app/services/livekit.py
and read them back via percentiles()/recent_samples()/list_op_types()
from an /analytics/latency route.
"""

import logging
import math
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sized for a single open /events SSE tab (one sample every 5s, see
# app/routes/events.py's poll loop, with no shared poller across tabs) to
# genuinely cover close to 24h of history: 24h * 3600s/h / 5s ~= 17280
# samples. 20000 rounds that up with headroom, still a trivially small
# amount of memory (~1.4MB of (float, float) tuples per op_type).
MAX_SAMPLES: int = 20000  # per op_type ring buffer size

_store: Dict[str, Deque[Tuple[float, float]]] = defaultdict(
    lambda: deque(maxlen=MAX_SAMPLES)
)


def record(op_type: str, latency_ms: float, ts: Optional[float] = None) -> None:
    """Append a (ts, latency_ms) sample for *op_type*.

    *ts* defaults to time.time() and is exposed as a parameter purely so
    tests can inject a specific timestamp.

    Recording a sample must never raise or slow down the call it's
    attached to (both app/services/livekit.py call sites invoke this
    bare, with no try/except of their own), so any failure here is
    logged and swallowed rather than propagated.
    """
    try:
        if ts is None:
            ts = time.time()
        _store[op_type].append((ts, latency_ms))
    except Exception:
        logger.warning("Failed to record latency sample for op_type=%s", op_type, exc_info=True)


def _nearest_rank(sorted_values: List[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted list of values.

    Avoids statistics.quantiles, which requires at least 2 data points
    and raises on a single sample.
    """
    n = len(sorted_values)
    index = max(0, math.ceil(pct / 100 * n) - 1)
    return sorted_values[index]


def _filter_by_window(
    samples: Deque[Tuple[float, float]], window_seconds: Optional[float]
) -> List[Tuple[float, float]]:
    """Return the (ts, latency_ms) pairs from *samples* within *window_seconds*.

    None means no windowing: return every sample.
    """
    if window_seconds is None:
        return list(samples)
    cutoff = time.time() - window_seconds
    return [(ts, latency) for ts, latency in samples if ts >= cutoff]


def percentiles(op_type: str, window_seconds: Optional[float] = None) -> Optional[dict]:
    """Return {"p50", "p90", "p99", "count"} over samples within the window.

    Returns None if there are zero samples in that window.
    """
    samples = _store.get(op_type)
    if not samples:
        return None

    filtered = _filter_by_window(samples, window_seconds)

    if not filtered:
        return None

    values = sorted(latency for _, latency in filtered)
    return {
        "p50": _nearest_rank(values, 50),
        "p90": _nearest_rank(values, 90),
        "p99": _nearest_rank(values, 99),
        "count": len(values),
    }


def recent_samples(
    op_type: str, window_seconds: Optional[float] = None, limit: int = 20
) -> List[Tuple[float, float]]:
    """Return the *limit* most recent (ts, latency_ms) pairs, newest-first."""
    samples = _store.get(op_type)
    if not samples:
        return []

    filtered = _filter_by_window(samples, window_seconds)

    filtered.sort(key=lambda pair: pair[0], reverse=True)
    return filtered[:limit]


def list_op_types() -> List[str]:
    """Return the op types that have at least one recorded sample."""
    return [op_type for op_type, samples in _store.items() if samples]


def oldest_sample_ts(op_type: str, window_seconds: Optional[float] = None) -> Optional[float]:
    """Return the timestamp of the oldest retained sample for *op_type*.

    Used to show the real coverage of a window (e.g. "showing the last 3h"
    for a "24h" selection) when the ring buffer doesn't actually hold that
    much history yet, or has evicted older samples under heavy load. When
    *window_seconds* is given, only samples within that window are
    considered -- i.e. this answers "how far back does the data actually
    shown for this window go", not "how far back does the buffer go in
    total". Returns None if there are no samples (in that window).
    """
    samples = _store.get(op_type)
    if not samples:
        return None

    filtered = _filter_by_window(samples, window_seconds)
    if not filtered:
        return None

    return min(ts for ts, _ in filtered)


def _reset_for_tests() -> None:
    """Clear all module state. Test-only; not used by application code."""
    _store.clear()
