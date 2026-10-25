# Plain-English Health Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the overview page a one-line, plain-English health headline ("LiveKit is healthy — responded in 42ms") instead of making the operator read raw numbers and infer status themselves.

**Architecture:** A small pure function in a new `health.py` service maps the `DashboardStats` the dashboard already gathers (`gather_dashboard_stats()`) into a headline + severity + a few plain-English context lines. It reuses the exact latency thresholds `app/services/anomaly.py` already uses (200ms / 500ms) so the wording never disagrees with the existing anomaly banner. Rendered as a new banner at the top of the existing `_health_summary.html.j2` partial, above the raw stat grid (which stays, unchanged).

**Tech Stack:** No new dependency.

**Spec:** No separate spec document — the user opted out of the brainstorming conversation for this work; scope and rationale are recorded in this plan and the originating conversation.

## Global Constraints

- Do not remove or restyle the existing raw-number stat grid in `_health_summary.html.j2` — this adds a headline above it, it does not replace it.
- Reuse the 200ms/500ms latency thresholds already encoded in `app/services/anomaly.py:31,38` rather than inventing new ones, so the plain-English headline and the existing anomaly observation never contradict each other for the same latency value.
- Only report a severity/status for signals this app actually measures (LiveKit reachability and latency, via `DashboardStats.error` and `DashboardStats.api_latency_ms`). Do not fabricate a healthy/degraded status for egress, ingress, or SIP — those have no failure signal available in `DashboardStats` today (an idle subsystem and a broken one both read as zero), so they appear only as plain informational counts, never as a severity claim.

## Review Focus

- `DashboardStats.error` set (LiveKit totally unreachable) must produce a "down" headline, not attempt to also read `api_latency_ms` (which is meaningless when the fatal rooms call itself failed).
- `api_latency_ms == 0.0` from a fresh/never-queried `DashboardStats()` (e.g., the zero-value fallback `overview.py:80` constructs when the gather itself raised) must not be misread as "0ms, extremely healthy" — treat it the same as the error case when `stats.error` is set, and as healthy (genuinely fast) otherwise, since 0.0 is also what a very fast real response rounds to.
- Exactly-at-threshold values (`api_latency_ms == 200` and `== 500`) must fall on the same side as `anomaly.py`'s existing `>` comparisons (not `>=`), so the two never disagree at the boundary.
- SIP-disabled deployments must not mention SIP at all in the context lines (matches existing `{% if sip_enabled() %}` gating elsewhere in this template).
- The banner must render without raising when `stats.platforms`/`stats.connection_types` or other optional fields are empty dicts (the dataclass defaults), since a freshly-started dashboard will have them empty.

---

## File Structure

- Create `app/services/health.py` — `evaluate(stats) -> HealthSummary`.
- Modify `app/routes/overview.py` — compute and pass `health_summary` to the template.
- Modify `app/templates/partials/_health_summary.html.j2` — render the headline banner.
- Tests: `tests/test_health.py`, extend `tests/test_main.py` or `tests/test_views.py` (whichever currently covers `/` — check before adding) for the rendered banner.

### Task 1: `health.evaluate()`

**Files:**
- Create: `app/services/health.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: `app.services.dashboard.DashboardStats` (existing fields: `error`, `api_latency_ms`, `rooms_total`, `rooms_active`, `participants_total`, `egress_active`, `ingress_active`, `sip_enabled`, `sip_trunks`).
- Produces:

```python
@dataclass
class HealthSummary:
    severity: str   # "down" | "degraded" | "healthy"
    headline: str
    details: list[str]

def evaluate(stats: DashboardStats) -> HealthSummary: ...
```

- [ ] **Step 1: Write failing tests**

```python
def test_evaluate_down_when_stats_has_error():
    stats = DashboardStats(error="connection refused")
    result = health.evaluate(stats)
    assert result.severity == "down"
    assert "connection refused" in result.headline

def test_evaluate_healthy_under_200ms():
    stats = DashboardStats(api_latency_ms=42.0, rooms_total=3, rooms_active=1, participants_total=2)
    result = health.evaluate(stats)
    assert result.severity == "healthy"
    assert "42" in result.headline

def test_evaluate_degraded_between_200_and_500ms():
    stats = DashboardStats(api_latency_ms=250.0)
    assert health.evaluate(stats).severity == "degraded"

def test_evaluate_down_above_500ms():
    stats = DashboardStats(api_latency_ms=600.0)
    assert health.evaluate(stats).severity == "down"

def test_evaluate_details_include_room_and_participant_counts():
    stats = DashboardStats(api_latency_ms=10.0, rooms_total=5, rooms_active=2, participants_total=7, egress_active=1, ingress_active=0)
    details = " ".join(health.evaluate(stats).details)
    assert "2" in details and "5" in details and "7" in details

def test_evaluate_omits_sip_when_disabled():
    stats = DashboardStats(api_latency_ms=10.0, sip_enabled=False, sip_trunks=3)
    details = " ".join(health.evaluate(stats).details)
    assert "SIP" not in details and "sip" not in details

def test_evaluate_includes_sip_when_enabled():
    stats = DashboardStats(api_latency_ms=10.0, sip_enabled=True, sip_trunks=2)
    details = " ".join(health.evaluate(stats).details)
    assert "2" in details and "SIP" in details
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement.** Severity: `"down"` if `stats.error` is truthy OR `api_latency_ms > 500`; `"degraded"` if `100 < api_latency_ms <= 500` (mirrors `anomaly.py`'s `> 200` "elevated" tier — use the same boundary, `> 200`, not `100`, to match exactly); `"healthy"` otherwise. (Use `anomaly.py`'s literal thresholds, `> 500` and `> 200`, copied as named constants `_CRITICAL_LATENCY_MS = 500` / `_WARNING_LATENCY_MS = 200` with a comment noting they mirror `app/services/anomaly.py`.) Headline text per severity as shown in the test assertions above. `details` is a list built unconditionally for rooms/participants/egress/ingress, and conditionally (only if `stats.sip_enabled`) for SIP trunks.

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/health.py tests/test_health.py && git commit -m "feat: add plain-English health summary"`

### Task 2: Surface on the overview page

**Files:**
- Modify: `app/routes/overview.py:93-99` (the `index.html.j2` render in the route that builds `health_stats`)
- Modify: `app/templates/partials/_health_summary.html.j2`
- Test: whichever existing test file covers `GET /` (check `tests/test_main.py` and `tests/test_views.py` first; add there)

**Interfaces:**
- Consumes: `health.evaluate(health_stats) -> HealthSummary` (Task 1).
- Produces: `index.html.j2`'s template context gains `health_summary`; `_health_summary.html.j2` gains a documented new parameter `health_summary` alongside its existing `health_stats`/`sip_enabled`.

- [ ] **Step 1: Write failing test**

```python
def test_overview_shows_plain_english_headline(client, auth_headers, monkeypatch):
    # mock lk so gather_dashboard_stats resolves with a known api_latency_ms
    resp = client.get("/", headers=auth_headers)
    assert b"healthy" in resp.content.lower() or b"LiveKit is" in resp.content
```

- [ ] **Step 2: Run test, confirm it fails.**

- [ ] **Step 3: Implement.** In the route handler ending at `overview.py:93-99`, add `health_summary = health.evaluate(health_stats)` right after the existing `observations = anomaly.detect(health_stats)` line, and add `"health_summary": health_summary` to the template context dict. In `_health_summary.html.j2`, insert a banner between the existing `{% if health_stats.error %}` block and the `stats-grid` div: a `<div class="alert alert-{{ 'danger' if health_summary.severity == 'down' else 'warning' if health_summary.severity == 'degraded' else 'success' }}">` containing `{{ health_summary.headline }}`, followed by a small `<ul>` of `health_summary.details`.

- [ ] **Step 4: Run tests, confirm they pass** — `pytest tests/test_main.py tests/test_views.py -v` (whichever file was extended).

- [ ] **Step 5: Commit** — `git add app/routes/overview.py app/templates/partials/_health_summary.html.j2 tests/test_main.py && git commit -m "feat: surface plain-English health headline on overview"`
