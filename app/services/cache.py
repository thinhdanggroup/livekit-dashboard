"""Simple module-level TTL cache for agent dispatch results.

Keyed by server URL so a configuration change automatically gets a fresh
cache. Lives at module scope so it survives across requests (a new
LiveKitClient is created per request, but the cache is not).
"""

import time
from typing import Any, Dict, List

TTL: float = 30.0        # seconds before a full re-fetch
CONCURRENCY: int = 10    # max parallel ListDispatch calls

_store: Dict[str, Dict[str, Any]] = {}


def get(url: str) -> Dict[str, Any]:
    """Return the cache entry for *url*, creating it if absent."""
    return _store.setdefault(url, {"data": [], "latency": 0.0, "ts": 0.0})


def set(url: str, data: List, latency: float) -> None:  # noqa: A001
    """Overwrite the cache entry for *url* with fresh data."""
    _store[url] = {"data": data, "latency": latency, "ts": time.monotonic()}


def invalidate(url: str) -> None:
    """Force the next read to bypass the cache for *url*."""
    if url in _store:
        _store[url]["ts"] = 0.0


def is_fresh(url: str) -> bool:
    """Return True if the cached value for *url* is still within TTL."""
    return time.monotonic() - _store.get(url, {}).get("ts", 0.0) < TTL
