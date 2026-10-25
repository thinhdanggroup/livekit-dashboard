"""In-memory ring-buffer store of per-op-type latency samples.

No persistence: this is a deliberate in-memory-only accumulator, same
tradeoff as the module-level TTL cache in app/services/cache.py. State
lives for the life of the process and resets on restart.

Callers (a later task) record latencies from app/services/livekit.py
and read them back via percentiles()/recent_samples()/list_op_types()
from an /analytics/latency route.
"""

import math
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

MAX_SAMPLES: int = 2000  # per op_type ring buffer size

_store: Dict[str, Deque[Tuple[float, float]]] = defaultdict(
    lambda: deque(maxlen=MAX_SAMPLES)
)


def record(op_type: str, latency_ms: float, ts: Optional[float] = None) -> None:
    """Append a (ts, latency_ms) sample for *op_type*.

    *ts* defaults to time.time() and is exposed as a parameter purely so
    tests can inject a specific timestamp.
    """
    if ts is None:
        ts = time.time()
    _store[op_type].append((ts, latency_ms))


def _nearest_rank(sorted_values: List[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted list of values.

    Avoids statistics.quantiles, which requires at least 2 data points
    and raises on a single sample.
    """
    n = len(sorted_values)
    index = max(0, math.ceil(pct / 100 * n) - 1)
    return sorted_values[index]


def percentiles(op_type: str, window_seconds: Optional[float] = None) -> Optional[dict]:
    """Return {"p50", "p90", "p99", "count"} over samples within the window.

    Returns None if there are zero samples in that window.
    """
    samples = _store.get(op_type)
    if not samples:
        return None

    if window_seconds is None:
        filtered = list(samples)
    else:
        cutoff = time.time() - window_seconds
        filtered = [(ts, latency) for ts, latency in samples if ts >= cutoff]

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

    if window_seconds is None:
        filtered = list(samples)
    else:
        cutoff = time.time() - window_seconds
        filtered = [(ts, latency) for ts, latency in samples if ts >= cutoff]

    filtered.sort(key=lambda pair: pair[0], reverse=True)
    return filtered[:limit]


def list_op_types() -> List[str]:
    """Return the op types that have at least one recorded sample."""
    return [op_type for op_type, samples in _store.items() if samples]


def _reset_for_tests() -> None:
    """Clear all module state. Test-only; not used by application code."""
    _store.clear()
