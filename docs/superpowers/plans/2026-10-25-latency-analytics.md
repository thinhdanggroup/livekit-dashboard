# Latency Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the operator a latency trend/percentile view (P50/P90/P99 over 1h/24h) instead of only the current-moment latency numbers scattered across other pages today.

**Architecture:** This app has no STT/LLM/TTS pipeline (it doesn't run voice agents), so there is no per-stage latency to break down — that part of the reference idea does not map onto real data here. What this app *does* already measure, on every call, is (a) the LiveKit API round-trip for `list_rooms()` and (b) the RTC connect time for `connect_to_room_for_stats()`. A new in-memory ring-buffer store (`latency_samples.py`, same module-level pattern as `app/services/cache.py`) records every one of those measurements as they already happen, tagged by operation type and timestamp. A new `/analytics/latency` page computes percentiles and a slowest-operations table from those samples.

**Tech Stack:** No new dependency. Python stdlib (`statistics.quantiles` or a hand-rolled percentile — plan author's call: use a small hand-rolled nearest-rank percentile function to avoid `statistics.quantiles`'s requirement of ≥2 data points and its different interpolation method, so a single sample doesn't raise).

**Spec:** No separate spec document — the user opted out of the brainstorming conversation for this work. The STT/LLM/TTS breakdown from the reference product is explicitly dropped as not applicable to this codebase; this is the plan author's scope call, recorded here rather than asked.

## Global Constraints

- No new dependency.
- Samples are kept **in-memory only** (not persisted to disk), following the precedent of `app/services/cache.py` — this is explicitly a bounded operational-telemetry buffer, not a database; a server restart resetting it is an accepted tradeoff, not a bug.
- Recording a sample must never be able to raise or slow down the call it's attached to — a ring buffer append is O(1) and wrapped so a recording failure can't break `list_rooms()` or `connect_to_room_for_stats()`, which are both on real user-facing request paths.
- Only report percentiles for the two operation types this app genuinely measures (`api_list_rooms`, `rtc_connect`) — do not add placeholder rows for STT/LLM/TTS.

## Review Focus

- Requesting a percentile for a window with zero samples (e.g., `rtc_connect` before anyone has ever opened a room's RTC stats) must return `None`/an empty state in the UI, not raise a `ZeroDivisionError` or `StatisticsError`.
- A single sample in the window must still produce a valid P50/P90/P99 (all equal to that one value), not raise — this rules out using `statistics.quantiles` directly without a guard, since it requires at least two data points.
- The ring buffer must actually bound memory: recording more than its max capacity must evict the oldest samples, not grow unbounded on a long-running server with the SSE poller hitting `list_rooms()` every 5 seconds indefinitely.
- The "1h" and "24h" window filters must correctly exclude samples older than the window, not silently fall back to "all time" — verify with a sample deliberately recorded with an old timestamp.
- The latency page must render a sensible empty state immediately after a fresh server start (zero samples for both op types), not a traceback.

---

## File Structure

- Create `app/services/latency_samples.py` — ring-buffer store + percentile math.
- Modify `app/services/livekit.py:51-58` (`list_rooms`) and `app/services/livekit.py:1535-1591` (`connect_to_room_for_stats`) — record a sample at each existing latency measurement point.
- Create `app/routes/analytics.py` — new `/analytics/latency` route.
- Create `app/templates/analytics/latency.html.j2`.
- Modify `app/main.py` — register the new router.
- Modify `app/templates/base.html.j2` — add the nav link.
- Tests: `tests/test_latency_samples.py`, `tests/test_analytics.py` (note: a file by this name may already exist for a different analytics route — check first and extend rather than overwrite if so), extend `tests/test_main.py` for router wiring if that's where such checks live.

### Task 1: Ring-buffer latency sample store

**Files:**
- Create: `app/services/latency_samples.py`
- Test: `tests/test_latency_samples.py`

**Interfaces:**
- Produces:
  - `record(op_type: str, latency_ms: float, ts: float | None = None) -> None` — `ts` defaults to `time.time()`; exposed as a parameter purely so tests can inject a specific timestamp. Appends to a per-`op_type` `collections.deque(maxlen=MAX_SAMPLES)`.
  - `MAX_SAMPLES: int = 2000` (module-level constant).
  - `percentiles(op_type: str, window_seconds: float | None = None) -> dict | None` — returns `{"p50": float, "p90": float, "p99": float, "count": int}` computed over samples within `window_seconds` of now (or all samples if `window_seconds is None`), or `None` if there are zero samples in that window.
  - `recent_samples(op_type: str, window_seconds: float | None = None, limit: int = 20) -> list[tuple[float, float]]` — the `limit` most recent `(ts, latency_ms)` pairs within the window, newest-first, for a "slowest recent operations" table built client-side from this (or pre-sorted by latency — plan author's call: return newest-first by time; the route sorts by latency descending for the "slowest" table so the raw accessor stays simple and reusable).
  - `list_op_types() -> list[str]` — the op types that have at least one recorded sample, for the page to iterate without hardcoding `["api_list_rooms", "rtc_connect"]` in two places.

- [ ] **Step 1: Write failing tests**

```python
def test_percentiles_none_when_no_samples():
    ls._reset_for_tests()  # test-only helper to clear module state between tests
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
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement.** Use `collections.deque(maxlen=MAX_SAMPLES)` per op type in a module-level `dict[str, deque]`, created via `collections.defaultdict`. Percentile math: sort the filtered `(ts, latency_ms)` list by `latency_ms`, use nearest-rank (`index = max(0, ceil(pct/100 * n) - 1)`) for p50/p90/p99 — this avoids `statistics.quantiles`'s 2-point minimum. Add a `_reset_for_tests()` function purely for test isolation (module-level state otherwise leaks between tests, same risk every module-level store in this codebase already has — `cache.py` has the same property and no reset helper, but this module's tests need one since percentile assertions are exact).

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/latency_samples.py tests/test_latency_samples.py && git commit -m "feat: add latency sample ring buffer and percentile calc"`

### Task 2: Record samples at the existing measurement points

**Files:**
- Modify: `app/services/livekit.py:51-58` (`list_rooms`), `app/services/livekit.py:1535-1591` (`connect_to_room_for_stats`)
- Test: extend `tests/test_main.py` or add to `tests/test_latency_samples.py` an integration-style test against `LiveKitClient`

**Interfaces:**
- Consumes: `latency_samples.record(op_type, latency_ms)` (Task 1).
- Produces: no change to either method's existing signature or return value — this only adds a side effect.

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_list_rooms_records_latency_sample(monkeypatch):
    ls._reset_for_tests()
    client = LiveKitClient()
    # monkeypatch client._get_api() to return a mock whose room.list_rooms returns an object with .rooms = []
    await client.list_rooms()
    assert ls.percentiles("api_list_rooms")["count"] == 1
```

- [ ] **Step 2: Run test, confirm it fails.**

- [ ] **Step 3: Implement.** In `list_rooms`, add `latency_samples.record("api_list_rooms", latency * 1000)` immediately after the existing `latency = time.perf_counter() - t0` line and before `return`. In `connect_to_room_for_stats`, add `latency_samples.record("rtc_connect", latency)` immediately before the existing `return stats, latency, error_msg` line (note: `latency` there is already in milliseconds, unlike in `list_rooms` where it's in seconds — do not re-multiply). Add `from app.services import latency_samples` to `livekit.py`'s imports.

- [ ] **Step 4: Run tests, confirm they pass.** Run the full `tests/test_rooms.py` and existing livekit-client test suites once to confirm the added import/calls don't break anything already passing.

- [ ] **Step 5: Commit** — `git add app/services/livekit.py tests/ && git commit -m "feat: record API and RTC latency samples"`

### Task 3: `/analytics/latency` page

**Files:**
- Create: `app/routes/analytics.py`
- Create: `app/templates/analytics/latency.html.j2`
- Modify: `app/main.py` (router registration)
- Modify: `app/templates/base.html.j2` (nav link)
- Test: `tests/test_analytics_latency.py` (check whether `tests/test_analytics.py` already exists for something else before naming — if it's free, use `tests/test_analytics.py` instead)

**Interfaces:**
- Consumes: `latency_samples.percentiles`, `latency_samples.recent_samples`, `latency_samples.list_op_types` (Task 1).
- Produces: `GET /analytics/latency` (admin-protected), accepting a `?window=1h|24h` query param (default `1h`).

- [ ] **Step 1: Write failing tests**

```python
def test_latency_page_requires_auth(client):
    resp = client.get("/analytics/latency", follow_redirects=False)
    assert resp.status_code == 401

def test_latency_page_empty_state(client, auth_headers):
    resp = client.get("/analytics/latency", headers=auth_headers)
    assert resp.status_code == 200
    assert b"No latency data" in resp.content or b"no data" in resp.content.lower()

def test_latency_page_shows_percentiles(client, auth_headers, monkeypatch):
    import app.services.latency_samples as ls
    ls._reset_for_tests()
    for v in [10, 20, 30]:
        ls.record("api_list_rooms", float(v))
    resp = client.get("/analytics/latency?window=24h", headers=auth_headers)
    assert b"api_list_rooms" in resp.content or b"P50" in resp.content
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement the route.** `window_seconds = 3600 if window == "1h" else 86400`. For each `op_type in latency_samples.list_op_types()`, build `{"op_type": op_type, "stats": latency_samples.percentiles(op_type, window_seconds), "slowest": sorted(latency_samples.recent_samples(op_type, window_seconds, limit=50), key=lambda s: s[1], reverse=True)[:10]}`. Pass the resulting list to the template along with `window`.

- [ ] **Step 4: Implement the template** — a card per op type with P50/P90/P99/count, and a "slowest recent operations" table (timestamp, latency) when `stats` is not `None`; an empty-state message per op type (or overall, if `list_op_types()` is empty) otherwise. A `window` toggle (two links/buttons for `1h`/`24h`) at the top.

- [ ] **Step 5: Register the router** in `app/main.py` (`from app.routes import ..., analytics` and `app.include_router(analytics.router, tags=["Analytics"])`) and add a sidebar link in `base.html.j2` next to the existing nav items (e.g., after `/diagnostics`), following the exact existing `<a href="..." class="nav-link {% if '/x' in request.url.path %}active{% endif %}">` pattern.

- [ ] **Step 6: Run tests, confirm they pass.**

- [ ] **Step 7: Commit** — `git add app/routes/analytics.py app/templates/analytics/latency.html.j2 app/main.py app/templates/base.html.j2 tests/ && git commit -m "feat: add latency percentile analytics page"`
