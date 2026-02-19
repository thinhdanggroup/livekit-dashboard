"""Homer/SIPCAPTURE client service — JWT auto-refresh, SIP call search and detail."""

import base64
import json
import os
import time
import httpx


# ---------------------------------------------------------------------------
# Module-level token cache (process-scoped, asyncio-safe for single-process)
# ---------------------------------------------------------------------------
_token: str | None = None
_token_exp: float = 0.0  # Unix timestamp


def _decode_exp(token: str) -> float:
    """Decode the JWT expiry from the middle (payload) segment without a JWT library."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return 0.0
        # Add padding so base64 decodes cleanly
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return float(payload.get("exp", 0))
    except Exception:
        return 0.0


async def _login(url: str, username: str, password: str) -> str:
    """POST /api/v3/auth and return the raw token string."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{url.rstrip('/')}/api/v3/auth",
            json={"username": username, "password": password, "type": "internal"},
        )
        resp.raise_for_status()
        data = resp.json()
        # Homer returns {"token": "..."} or the token at top level
        if isinstance(data, dict):
            return data.get("token") or data.get("data", {}).get("token", "")
        return str(data)


async def _ensure_token(url: str, username: str, password: str) -> str:
    """Return a valid JWT, re-authenticating if it is expired or about to expire."""
    global _token, _token_exp
    if _token and time.time() < _token_exp - 60:
        return _token
    _token = await _login(url, username, password)
    _token_exp = _decode_exp(_token)
    # If exp couldn't be decoded, cache for 1 hour as a safe default
    if _token_exp == 0.0:
        _token_exp = time.time() + 3600
    return _token


# ---------------------------------------------------------------------------
# Public API methods
# ---------------------------------------------------------------------------


def _build_homer_filters(filters: dict) -> list[dict]:
    """
    Convert our filter dict to Homer's native server-side filter format.

    Homer expects an array of filter objects:
      [{"name": "data_header.<field>", "value": "...", "func": null, "type": "string", "hepid": 1}]

    An empty list [] means "no filter" (return all records).
    """
    field_map = {
        "callid":    "data_header.callid",
        "from_user": "data_header.from_user",
        "to_user":   "data_header.to_user",
        "method":    "data_header.method",
        "source_ip": "data_header.src_ip",
        "dst_ip":    "data_header.dst_ip",
        "from_tag":  "data_header.from_tag",
        "to_tag":    "data_header.to_tag",
    }
    result = []
    for key, field_name in field_map.items():
        val = (filters.get(key) or "").strip()
        if val:
            result.append({"name": field_name, "value": val, "func": None, "type": "string", "hepid": 1})
    return result


async def search_calls(
    url: str,
    token: str,
    filters: dict,
    time_from_ms: int,
    time_to_ms: int,
    limit: int = 200,
) -> tuple[list[dict], float]:
    """
    POST /api/v3/search/call/data using Homer's native filter format.

    filters: dict with optional keys callid, from_user, to_user, method,
             source_ip, dst_ip, from_tag, to_tag.
    """
    payload = {
        "config": {
            "protocol_id": {"name": "SIP", "value": 1},
            "protocol_profile": {"name": "call", "value": "call"},
            "searchbutton": False,
            "title": "CALL 2 SIP SEARCH",
        },
        "param": {
            "transaction": {},
            "limit": limit,
            "orlogic": False,
            "search": {"1_call": _build_homer_filters(filters)},
            "location": {},
            "timezone": {"value": -180, "name": "Local"},
        },
        "timestamp": {"from": time_from_ms, "to": time_to_ms},
        "fields": [],
    }

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
        resp = await client.post(
            f"{url.rstrip('/')}/api/v3/search/call/data",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/plain, */*",
            },
        )
        if not resp.is_success:
            body = resp.text[:500]
            raise RuntimeError(f"Homer search returned HTTP {resp.status_code}: {body}")
        data = resp.json()
    latency_ms = (time.perf_counter() - t0) * 1000

    # Unwrap Homer's response envelope
    records: list[dict] = []
    if isinstance(data, dict):
        inner = data.get("data") or data.get("results") or []
        if isinstance(inner, list):
            records = inner
        elif isinstance(inner, dict):
            for v in inner.values():
                if isinstance(v, list):
                    records.extend(v)

    return records, latency_ms


async def get_call_transaction(
    url: str,
    token: str,
    callid: str,
    record_id: int | str,
    ts_ms: int,
    window_ms: int = 3_600_000,
) -> tuple[dict, float]:
    """POST /api/v3/call/transaction and return (response_dict, latency_ms).

    window_ms controls the half-width of the timestamp search window around ts_ms.
    Use a wider value (e.g. 30 * 24 * 3_600_000) when the call timestamp is unknown.
    """
    payload = {
        "param": {
            "transaction": {"call": True, "registration": False, "rest": False},
            "limit": 200,
            "orlogic": False,
            "search": {"1_call": {"id": record_id, "callid": [callid]}},
            "location": {},
            "timezone": {"value": -180, "name": "Local"},
        },
        "timestamp": {
            "from": ts_ms - window_ms,
            "to": ts_ms + window_ms,
        },
    }

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{url.rstrip('/')}/api/v3/call/transaction",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
    latency_ms = (time.perf_counter() - t0) * 1000
    return data, latency_ms


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


class HomerClient:
    """Thin holder for config + authenticated token. Returned by get_homer_client()."""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token

    async def search_calls(
        self,
        filters: dict,
        time_from_ms: int,
        time_to_ms: int,
        limit: int = 200,
    ) -> tuple[list[dict], float]:
        return await search_calls(self.url, self.token, filters, time_from_ms, time_to_ms, limit)

    async def get_call_transaction(
        self, callid: str, record_id: int | str, ts_ms: int, window_ms: int = 3_600_000
    ) -> tuple[dict, float]:
        return await get_call_transaction(self.url, self.token, callid, record_id, ts_ms, window_ms)


async def get_homer_client() -> HomerClient:
    """FastAPI Depends-compatible factory. Raises RuntimeError when Homer is not configured."""
    homer_url = os.environ.get("HOMER_URL", "").strip()
    homer_user = os.environ.get("HOMER_USERNAME", "").strip()
    homer_pass = os.environ.get("HOMER_PASSWORD", "").strip()

    if not (homer_url and homer_user and homer_pass):
        raise RuntimeError(
            "Homer is not configured. Set HOMER_URL, HOMER_USERNAME, and HOMER_PASSWORD."
        )

    token = await _ensure_token(homer_url, homer_user, homer_pass)
    return HomerClient(url=homer_url, token=token)
