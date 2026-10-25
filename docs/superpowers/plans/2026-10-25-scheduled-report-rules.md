# Scheduled Report Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator define rules that automatically deliver a dashboard-stats digest on a schedule (every N minutes, or daily at a given time), reusing the single webhook delivery channel this app already has — no email, since this app has no email infrastructure to build on.

**Architecture:** CRUD-managed `ReportRule` records in a new JSON-file store (`report_rules.py`), structured exactly like the existing `app/services/alerts.py` rule store. A background `asyncio` task, started in `app/main.py`'s existing `lifespan` context manager, wakes once a minute, finds due rules, gathers the same `DashboardStats` + `anomaly` observations the overview page already computes, and posts a digest to the single `webhook_url` configured in `app/services/notifications.py` — using the shared `post_json()` helper and `webhook_log` store introduced in the webhook-delivery-log plan, so every report send is visible in that same log. A new `/reports` page, modeled directly on `/alerts`, manages the rules.

**Tech Stack:** No new dependency — `asyncio.create_task` inside the existing `lifespan` context manager, not APScheduler or Celery (this codebase has no background-job dependency today and one minute-granularity poll loop doesn't need one).

**Spec:** No separate spec document — the user opted out of the brainstorming conversation for this work. Scope calls made here without asking: webhook delivery only (no email, since none exists in this app); a misconfigured rule (no webhook URL set) still "runs" on schedule and logs a visible failure in the webhook delivery log rather than silently never firing or retrying every minute forever.

**Depends on:** `docs/superpowers/plans/2026-10-25-webhook-delivery-log.md` (Task 1's `post_json` helper and Task 2's `webhook_log.log_delivery`) — build that plan first.

## Global Constraints

- No new dependency.
- `report_rules.py` must `import app.utils.http as http_util` and call `http_util.post_json(...)` (not `from app.utils.http import post_json`) — see the webhook-delivery-log plan's Global Constraints for why; tests patch `app.utils.http.post_json` and that only intercepts module-attribute access.
- Follow `app/services/alerts.py`'s exact CRUD/dataclass/JSON-file pattern for `report_rules.py`.
- All times are UTC, matching every other timestamp already produced in this codebase (`datetime.now(timezone.utc)`).
- The background loop must never let one failing rule (bad URL, LiveKit unreachable) stop the loop from checking other rules or from running again next minute — each rule's run is wrapped so one failure is isolated.

## Review Focus

- A `"daily"` rule whose target time has already passed today, with no prior `last_run`, must fire once today (not wait until tomorrow) — the "catch up once per day after the target time" semantics must actually be implemented, not just described.
- A `"daily"` rule must fire **once** per calendar day even though the loop polls every 60 seconds past the target time — `is_due` must become `False` again immediately after `mark_run` records today's date, or it would fire on every poll for the rest of the day.
- An `"interval"` rule with `interval_minutes=1` polled by a 60-second loop must not double-fire or skip a cycle due to clock drift between "now" and "last_run" — use `>=` on the elapsed-time comparison, not `>`.
- A rule with no webhook URL configured (`notifications.get_config()["webhook_url"] == ""`) must still be marked as run (so it doesn't retry every minute) and must still produce a visible, inspectable failure record in `webhook_log`, not fail silently with nothing for the operator to find.
- Deleting or disabling a rule must take effect on the very next scheduler tick (within 60 seconds), not require an app restart — this falls out naturally from loading rules fresh from disk every tick, but must be verified, not assumed.

---

## File Structure

- Create `app/services/report_rules.py` — CRUD store, due-check logic, digest builder, the run/scheduler functions.
- Modify `app/main.py` — start/stop the background loop in `lifespan`.
- Create `app/routes/report_rules.py` — `/reports` CRUD routes, modeled on `app/routes/alerts.py`.
- Create `app/templates/reports/index.html.j2`, modeled on `app/templates/alerts/index.html.j2`.
- Modify `app/templates/base.html.j2` — nav link.
- Tests: `tests/test_report_rules.py`, `tests/test_report_rules_routes.py`.

### Task 1: `ReportRule` CRUD store and due-check logic

**Files:**
- Create: `app/services/report_rules.py`
- Test: `tests/test_report_rules.py`

**Interfaces:**
- Produces:

```python
@dataclass
class ReportRule:
    id: str
    name: str
    schedule_type: str        # "interval" | "daily"
    interval_minutes: int | None = None
    daily_time: str | None = None   # "HH:MM", 24h, UTC
    enabled: bool = True
    last_run: str = ""        # ISO timestamp, UTC, or "" if never run

SCHEDULE_TYPES = ["interval", "daily"]

def list_rules() -> list[ReportRule]: ...
def get_rule(rule_id: str) -> ReportRule | None: ...
def create_rule(name: str, schedule_type: str, interval_minutes: int | None = None, daily_time: str | None = None) -> ReportRule: ...
def delete_rule(rule_id: str) -> bool: ...
def toggle_rule(rule_id: str) -> bool | None: ...
def is_due(rule: ReportRule, now: datetime) -> bool: ...
def mark_run(rule_id: str, now_iso: str) -> None: ...
```

`create_rule` raises `ValueError` if `schedule_type` isn't in `SCHEDULE_TYPES`, if `schedule_type == "interval"` and `interval_minutes` isn't a positive int, or if `schedule_type == "daily"` and `daily_time` doesn't match `HH:MM` (validate with a simple regex or `datetime.strptime(daily_time, "%H:%M")` in a try/except).

- [ ] **Step 1: Write failing tests**

```python
def test_create_rule_rejects_bad_schedule_type(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        with pytest.raises(ValueError):
            rr.create_rule("x", "weekly")

def test_create_interval_rule_requires_minutes(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        with pytest.raises(ValueError):
            rr.create_rule("x", "interval", interval_minutes=0)

def test_create_daily_rule_requires_valid_time(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        with pytest.raises(ValueError):
            rr.create_rule("x", "daily", daily_time="25:99")

def test_interval_rule_due_when_never_run(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=10)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is True

def test_interval_rule_not_due_before_elapsed(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=10)
        rr.mark_run(rule.id, datetime.now(timezone.utc).isoformat())
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is False

def test_interval_rule_due_after_elapsed(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=10)
        ten_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        rr.mark_run(rule.id, ten_min_ago)
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is True

def test_daily_rule_due_once_past_target_time_then_not_again_same_day(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "daily", daily_time="00:00")  # always past target
        now = datetime.now(timezone.utc)
        assert rr.is_due(rule, now) is True
        rr.mark_run(rule.id, now.isoformat())
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, now) is False

def test_daily_rule_not_due_before_target_time(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "daily", daily_time="23:59")
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)  # before 23:59
    assert rr.is_due(rule, now) is False

def test_disabled_rule_never_due(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=1)
        rr.toggle_rule(rule.id)  # disable
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is False
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement**, mirroring `app/services/alerts.py`'s `_load`/`_save`/dataclass/`id=str(uuid.uuid4())[:8]` structure. `is_due`: for `"interval"`, `True` if `rule.last_run == ""` or `now - datetime.fromisoformat(rule.last_run) >= timedelta(minutes=rule.interval_minutes)`; for `"daily"`, `True` if `now.strftime("%H:%M") >= rule.daily_time` and (`rule.last_run == ""` or `datetime.fromisoformat(rule.last_run).date() != now.date()`); always `False` if `not rule.enabled`.

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/report_rules.py tests/test_report_rules.py && git commit -m "feat: add report rule store and due-check logic"`

### Task 2: Digest builder and the run/scheduler functions

**Files:**
- Modify: `app/services/report_rules.py` (same file, additive)
- Test: extend `tests/test_report_rules.py`

**Interfaces:**
- Consumes: `app.services.dashboard.gather_dashboard_stats(lk) -> DashboardStats`, `app.services.anomaly.detect(stats) -> list[Observation]`, `app.services.notifications.get_config() -> dict`, `app.utils.http.post_json(url, payload) -> dict`, `app.services.webhook_log.log_delivery(...)`.
- Produces:

```python
def build_digest(rule_name: str, stats: DashboardStats, observations: list) -> str: ...
async def run_rule_now(rule: ReportRule, lk: LiveKitClient) -> dict: ...  # runs one rule unconditionally, marks it run, logs delivery; returns {"rule_id", "status", "error"}
async def run_due_rules(lk: LiveKitClient, now: datetime | None = None) -> list[dict]: ...  # finds due rules and calls run_rule_now on each
async def run_scheduler_loop(interval_seconds: int = 60) -> None: ...  # never returns; runs until cancelled
```

`run_due_rules` is a thin wrapper: it loads `list_rules()`, filters to `is_due(rule, now or datetime.now(timezone.utc))`, and calls `run_rule_now(rule, lk)` for each, collecting results. `run_rule_now` holds all the digest/delivery/logging/mark-run logic described below, so the `/reports` page's "run now" action (Task 4) can call it directly on a single rule without duplicating that body.

`run_due_rules` returns one `{"rule_id": str, "status": int | None, "error": str | None}` per rule it ran (empty list if nothing was due), for testability without needing to inspect `webhook_log` indirectly.

- [ ] **Step 1: Write failing tests**

```python
def test_build_digest_includes_stats_and_observations():
    stats = DashboardStats(rooms_total=3, rooms_active=1, api_latency_ms=42.0)
    obs = [anomaly.Observation(severity="warning", title="t", detail="d")]
    payload = json.loads(rr.build_digest("Daily Summary", stats, obs))
    assert payload["report"] == "Daily Summary"
    assert payload["stats"]["rooms_total"] == 3
    assert payload["observations"][0]["title"] == "t"

@pytest.mark.asyncio
async def test_run_due_rules_posts_and_logs(tmp_path, monkeypatch):
    # patch report_rules._STORE_PATH, notifications._STORE_PATH, webhook_log._STORE_PATH to tmp_path files
    # notifications.save_config(webhook_url="http://example.com/hook")
    # create an interval rule with interval_minutes=1 (never run -> due)
    # patch app.utils.http.post_json to return {"status": 200, "body": "", "error": None}
    # patch app.services.dashboard.gather_dashboard_stats to return a canned DashboardStats via AsyncMock
    results = await rr.run_due_rules(lk=MagicMock())
    assert results[0]["status"] == 200
    # assert the rule's last_run is now set, and webhook_log has one "report_rule"-sourced entry

@pytest.mark.asyncio
async def test_run_due_rules_logs_failure_when_no_webhook_configured(tmp_path, monkeypatch):
    # no notifications.save_config called -> webhook_url == ""
    # create a due rule
    results = await rr.run_due_rules(lk=MagicMock())
    assert results[0]["error"]
    # assert last_run was still set (rule.get_rule(...).last_run != "") despite the failure

@pytest.mark.asyncio
async def test_run_due_rules_skips_not_due_and_disabled():
    # a rule that just ran (not due) and a disabled rule both produce no entries in the result
    ...
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement.** `build_digest` returns `json.dumps({"source": "livekit-dashboard", "report": rule_name, "generated_at": <now iso>, "stats": {the same fields DashboardStats exposes, pulled via dataclasses.asdict or explicit dict}, "observations": [dataclasses.asdict(o) for o in observations]})`.

`run_rule_now(rule, lk)`: wrap the whole body in `try/except Exception as exc`, with `result = {"status": None, "error": str(exc)}` on failure, and a `finally` that always calls `mark_run(rule.id, datetime.now(timezone.utc).isoformat())` so a crash mid-run still marks it run (no infinite immediate-retry on the next tick). Inside the `try`: `stats = await gather_dashboard_stats(lk)`; `observations = anomaly.detect(stats)`; `payload = build_digest(rule.name, stats, observations)`; `url = notifications.get_config().get("webhook_url", "").strip()`; if `url`: `result = http_util.post_json(url, payload)` else `result = {"status": None, "error": "no webhook_url configured"}`; `webhook_log.log_delivery("report_rule", url, payload, result.get("status"), result.get("error"))`. Return `{"rule_id": rule.id, "status": result.get("status"), "error": result.get("error")}`.

`run_due_rules(lk, now=None)`: `now = now or datetime.now(timezone.utc)`; return `[await run_rule_now(rule, lk) for rule in list_rules() if is_due(rule, now)]`.

`run_scheduler_loop`: `while True: try: await run_due_rules(LiveKitClient()) except Exception: pass; await asyncio.sleep(interval_seconds)`.

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/report_rules.py tests/test_report_rules.py && git commit -m "feat: run due report rules and deliver digests via webhook"`

### Task 3: Start the scheduler loop at app startup

**Files:**
- Modify: `app/main.py` (`lifespan`)
- Test: a lightweight smoke test confirming the app still starts and shuts down cleanly with the task running (extend `tests/test_main.py`)

**Interfaces:**
- Consumes: `report_rules.run_scheduler_loop()` (Task 2).

- [ ] **Step 1: Write failing test**

```python
def test_app_starts_and_stops_with_scheduler_task(client):
    # the `client` fixture already enters/exits the TestClient context manager,
    # which runs the lifespan startup/shutdown; this just needs to not hang or raise
    resp = client.get("/health")
    assert resp.status_code == 200
```

(This test mostly already passes via the existing `client` fixture; its purpose is to catch the scheduler task preventing clean shutdown once added — run it after Step 3's change, not before, to confirm no regression.)

- [ ] **Step 2: Implement.** In `lifespan`, after the existing startup prints, add `scheduler_task = asyncio.create_task(report_rules.run_scheduler_loop())`; after `yield`, before/alongside the existing shutdown print, add `scheduler_task.cancel()` followed by `with contextlib.suppress(asyncio.CancelledError): await scheduler_task` (import `contextlib` and `asyncio` — `asyncio` is likely already imported in `main.py`; check first).

- [ ] **Step 3: Run the full test suite** (`pytest tests/ -v`) to confirm no test hangs waiting on the new background task — every test using the `client` fixture now starts/stops it once per test.

- [ ] **Step 4: Commit** — `git add app/main.py tests/test_main.py && git commit -m "feat: start report-rule scheduler loop at app startup"`

### Task 4: `/reports` CRUD page

**Files:**
- Create: `app/routes/report_rules.py`, modeled directly on `app/routes/alerts.py`
- Create: `app/templates/reports/index.html.j2`, modeled directly on `app/templates/alerts/index.html.j2`
- Modify: `app/main.py` (router registration), `app/templates/base.html.j2` (nav link)
- Test: `tests/test_report_rules_routes.py`

**Interfaces:**
- Consumes: `report_rules.list_rules/create_rule/delete_rule/toggle_rule` (Task 1).
- Produces: `GET /reports`, `POST /reports` (create), `POST /reports/{rule_id}/delete`, `POST /reports/{rule_id}/toggle`, `POST /reports/{rule_id}/run-now` (looks up the rule via `report_rules.get_rule(rule_id)` and calls `report_rules.run_rule_now(rule, lk)` directly — unconditionally, ignoring `is_due`, which is exactly what `run_rule_now` already does since the due-check lives only in `run_due_rules`).

- [ ] **Step 1: Write failing tests**

```python
def test_reports_page_requires_auth(client):
    resp = client.get("/reports", follow_redirects=False)
    assert resp.status_code == 401

def test_create_and_list_report_rule(client, auth_headers):
    client.post("/reports", headers=auth_headers,
                data={"csrf_token": _csrf(), "name": "Daily Digest", "schedule_type": "daily", "daily_time": "09:00"})
    resp = client.get("/reports", headers=auth_headers)
    assert b"Daily Digest" in resp.content

def test_toggle_and_delete_report_rule(client, auth_headers):
    client.post("/reports", headers=auth_headers,
                data={"csrf_token": _csrf(), "name": "x", "schedule_type": "interval", "interval_minutes": "60"})
    import app.services.report_rules as rr
    rule_id = rr.list_rules()[0].id
    client.post(f"/reports/{rule_id}/toggle", headers=auth_headers, data={"csrf_token": _csrf()})
    assert rr.get_rule(rule_id).enabled is False
    client.post(f"/reports/{rule_id}/delete", headers=auth_headers, data={"csrf_token": _csrf()})
    assert rr.get_rule(rule_id) is None

def test_run_now_fires_regardless_of_schedule(client, auth_headers, monkeypatch):
    # create a rule, patch post_json, POST .../run-now, assert a webhook_log entry with source "report_rule" exists
    ...
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement the routes**, following `app/routes/alerts.py`'s structure line-for-line (CSRF verify, try/except ValueError swallow on create, redirect 303 back to `/reports` after every mutation). `run-now` route uses `get_livekit_client` dependency like other routes that need an `lk`.

- [ ] **Step 4: Implement the template** — a form to create a rule (name, a `schedule_type` select, an `interval_minutes` number input and a `daily_time` time input both always present with helper text saying which applies to which type — simplest valid UI, no conditional JS required) and a table of existing rules (name, schedule description, last run, enabled toggle, delete, run-now), respecting `{% if not is_readonly() %}` around mutating controls.

- [ ] **Step 5: Register the router** in `main.py` and add the nav link in `base.html.j2`.

- [ ] **Step 6: Run tests, confirm they pass.**

- [ ] **Step 7: Commit** — `git add app/routes/report_rules.py app/templates/reports/index.html.j2 app/main.py app/templates/base.html.j2 tests/test_report_rules_routes.py && git commit -m "feat: add report rules management page"`
