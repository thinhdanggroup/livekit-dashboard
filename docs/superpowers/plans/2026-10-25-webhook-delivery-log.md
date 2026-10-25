# Webhook Delivery Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a history of every outbound webhook POST this dashboard sends (alert fires, manual diagnostics tests, and future report-rule sends), show it as a table, and let an operator replay any past delivery.

**Architecture:** A new append-only JSON-file service (`webhook_log.py`) following the existing `audit_log.py` pattern. A new shared `post_json()` helper replaces three near-duplicate urllib POST blocks (notifications, diagnostics, and the future report-rules sender) so every webhook send goes through one code path that can be logged. `diagnostics.py` gains a log table and a replay route; `notifications.fire_webhook()` logs automatically.

**Tech Stack:** Python stdlib `urllib.request` (already in use, no new dependency), existing FastAPI/Jinja stack.

**Spec:** No separate spec document — the user opted out of the brainstorming conversation for this work; scope and rationale are recorded in this plan's Goal/Architecture and in the originating conversation.

## Global Constraints

- Every consumer of `post_json` must `import app.utils.http as http_util` (or `from app.utils import http as http_util`) and call `http_util.post_json(...)` — never `from app.utils.http import post_json`. Tests patch `app.utils.http.post_json` directly; that only intercepts calls made through the module object, not a name imported into another module's namespace at import time.
- No new third-party dependency.
- Follow the existing JSON-file store pattern (env-var configurable path, `_load`/`_save`, trimmed to a max entry count) used by `app/services/audit_log.py` and `app/services/notifications.py`.
- All new routes require `requires_admin` and CSRF verification, matching every other mutating route in this app.
- Payloads and URLs in the log are operator-entered or internally generated — never render them unescaped outside Jinja's default autoescaping (no `|safe`).

## Review Focus

- A webhook URL pointing at an unreachable host or timing out must still be logged (with `error` set), not raise and crash the request.
- Replaying a log entry whose `id` no longer exists (log was trimmed) must redirect cleanly, not 500.
- A payload containing HTML/JS must render as inert text in the log table (autoescape), not execute.
- The log file growing past `MAX_ENTRIES` must trim oldest-first, matching `audit_log.py` behavior, so the store can't grow unbounded.
- Concurrent writes (an alert fire and a manual test landing in the same second) must not corrupt the JSON file — rely on the existing load-modify-save-whole-file pattern already used elsewhere in this codebase (no new concurrency primitive needed, consistent with current guarantees).

---

## File Structure

- Create `app/utils/http.py` — shared `post_json()` helper.
- Create `app/services/webhook_log.py` — append-only delivery log store.
- Modify `app/services/notifications.py` — use `post_json()`, log every send.
- Modify `app/routes/diagnostics.py` — use `post_json()`, log manual tests, add replay route, pass log entries to the template.
- Modify `app/templates/diagnostics/index.html.j2` — render the delivery log table with a replay button per row.
- Tests: `tests/test_http_util.py`, `tests/test_webhook_log.py`, extend `tests/test_notifications.py` and `tests/test_diagnostics.py`.

### Task 1: Shared `post_json()` helper

**Files:**
- Create: `app/utils/http.py`
- Test: `tests/test_http_util.py`

**Interfaces:**
- Produces: `post_json(url: str, payload: str, timeout: float = 5.0) -> dict` returning `{"status": int | None, "body": str, "error": str | None}`. On success, `body` is the response body truncated to 512 chars, `error` is `None`. On an `HTTPError`, `status` is the HTTP code, `body` is up to 256 chars of the error body, `error` is `None` (an HTTP error response is still a completed delivery, not a transport failure). On any other exception (timeout, DNS failure, connection refused), `status` is `None`, `body` is `""`, `error` is `str(exc)`.

- [ ] **Step 1: Write failing tests**

```python
def test_post_json_success(monkeypatch):
    # patch urllib.request.urlopen to a context-manager mock returning status=200, body=b"ok"
    result = post_json("http://example.com", "{}")
    assert result == {"status": 200, "body": "ok", "error": None}

def test_post_json_http_error(monkeypatch):
    # patch urlopen to raise urllib.error.HTTPError(..., code=404, ...)
    result = post_json("http://example.com", "{}")
    assert result["status"] == 404
    assert result["error"] is None

def test_post_json_connection_error(monkeypatch):
    # patch urlopen to raise OSError("Connection refused")
    result = post_json("http://example.com", "{}")
    assert result["status"] is None
    assert "Connection refused" in result["error"]
```

- [ ] **Step 2: Run tests, confirm they fail** — `pytest tests/test_http_util.py -v` → FAIL (module not found).

- [ ] **Step 3: Implement `post_json`** in `app/utils/http.py`. Port the existing try/except block from `app/routes/diagnostics.py:test_webhook` (urllib.request.Request with `Content-Type: application/json` and `User-Agent: livekit-dashboard/1.0` headers, POST method) almost verbatim — this is the exact logic being consolidated.

- [ ] **Step 4: Run tests, confirm they pass** — `pytest tests/test_http_util.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add app/utils/http.py tests/test_http_util.py && git commit -m "feat: add shared post_json http helper"`

### Task 2: Webhook delivery log store

**Files:**
- Create: `app/services/webhook_log.py`
- Test: `tests/test_webhook_log.py`

**Interfaces:**
- Consumes: nothing (pure JSON-file store, same shape as `app/services/audit_log.py`).
- Produces:
  - `log_delivery(source: str, url: str, payload: str, status: int | None, error: str | None) -> str` — appends an entry, returns its generated `id`.
  - `list_entries(limit: int = 100) -> list[dict]` — newest-first.
  - `get_entry(entry_id: str) -> dict | None`.
  - Entry shape: `{"id": str, "ts": iso-str, "source": str, "url": str, "payload": str, "status": int | None, "error": str | None}`. `source` is one of `"alert"`, `"manual_test"`, `"replay"`, `"report_rule"` (free string, not enforced — callers control it).
- `_STORE_PATH` from env var `WEBHOOK_LOG_FILE`, default `/tmp/webhook_log.json`. `MAX_ENTRIES = 200`.

- [ ] **Step 1: Write failing tests** (mirror `tests/test_audit.py`'s `patch.object(module, "_STORE_PATH", ...)` pattern):

```python
def test_list_entries_empty(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")):
        assert wl.list_entries() == []

def test_log_delivery_persists_and_lists_newest_first(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")):
        wl.log_delivery("manual_test", "http://a", "{}", 200, None)
        entry_id = wl.log_delivery("alert", "http://b", "{}", None, "timeout")
        entries = wl.list_entries()
    assert len(entries) == 2
    assert entries[0]["source"] == "alert"  # newest first
    assert entries[0]["id"] == entry_id

def test_get_entry_found_and_missing(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")):
        entry_id = wl.log_delivery("manual_test", "http://a", "{}", 200, None)
        assert wl.get_entry(entry_id)["url"] == "http://a"
        assert wl.get_entry("doesnotexist") is None

def test_log_trims_to_max_entries(tmp_path):
    with patch.object(wl, "_STORE_PATH", str(tmp_path / "wh.json")), patch.object(wl, "MAX_ENTRIES", 3):
        for i in range(5):
            wl.log_delivery("manual_test", f"http://{i}", "{}", 200, None)
        assert len(wl.list_entries(limit=10)) == 3
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement** `app/services/webhook_log.py` following `app/services/audit_log.py`'s `_load`/`_save`/trim structure exactly; generate `id` with `str(uuid.uuid4())[:8]` (same style as `app/services/alerts.py`).

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/webhook_log.py tests/test_webhook_log.py && git commit -m "feat: add webhook delivery log store"`

### Task 3: Wire logging into `notifications.fire_webhook`

**Files:**
- Modify: `app/services/notifications.py`
- Test: extend `tests/test_notifications.py` (create it if it doesn't exist yet, following `tests/test_audit.py`'s structure)

**Interfaces:**
- Consumes: `app.utils.http.post_json(url, payload, timeout=5.0) -> dict` (Task 1), `app.services.webhook_log.log_delivery(...)` (Task 2).
- Produces: `fire_webhook()`'s existing public signature and return value are unchanged — only its internals and side effects change.

- [ ] **Step 1: Write failing test**

```python
def test_fire_webhook_logs_delivery(tmp_path, monkeypatch):
    import app.services.notifications as notif
    import app.services.webhook_log as wl
    monkeypatch.setattr(notif, "_STORE_PATH", str(tmp_path / "n.json"))
    monkeypatch.setattr(wl, "_STORE_PATH", str(tmp_path / "wh.json"))
    notif.save_config(webhook_url="http://example.com/hook")
    rule = SimpleNamespace(id="r1", name="x", metric="rooms_total", operator=">", threshold=1, severity="warning")
    with patch("app.utils.http.post_json", return_value={"status": 200, "body": "", "error": None}):
        notif.fire_webhook([rule], force=True)
    entries = wl.list_entries()
    assert len(entries) == 1
    assert entries[0]["source"] == "alert"
    assert entries[0]["status"] == 200
```

- [ ] **Step 2: Run test, confirm it fails.**

- [ ] **Step 3: Implement** — add `import app.utils.http as http_util` to `notifications.py`; replace `fire_webhook`'s inline `urllib.request` try/except block with a call to `http_util.post_json(url, payload.decode())`, mapping its return dict to the function's existing `{"status":..., "error":...}` result shape; immediately after computing `result`, call `webhook_log.log_delivery("alert", url, payload.decode(), result.get("status"), result.get("error"))`.

- [ ] **Step 4: Run test, confirm it passes.** Also run the full existing `tests/test_alerts.py` suite to confirm no regression: `pytest tests/test_alerts.py tests/test_notifications.py -v`.

- [ ] **Step 5: Commit** — `git add app/services/notifications.py tests/test_notifications.py && git commit -m "feat: log every alert webhook delivery"`

### Task 4: Delivery log view, manual-test logging, and replay route

**Files:**
- Modify: `app/routes/diagnostics.py`
- Modify: `app/templates/diagnostics/index.html.j2`
- Test: extend `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `post_json` (Task 1), `webhook_log.log_delivery` / `list_entries` / `get_entry` (Task 2).
- Produces: `GET /diagnostics` and `POST /diagnostics/webhook-test` both now include `webhook_log_entries: list[dict]` in their template context (`webhook_log.list_entries(limit=50)`). New route `POST /diagnostics/webhook-log/{entry_id}/replay`.

- [ ] **Step 1: Write failing tests**

```python
def test_diagnostics_page_includes_log_table(client, auth_headers):
    resp = client.get("/diagnostics", headers=auth_headers)
    assert b"Webhook Delivery Log" in resp.content

def test_webhook_test_creates_log_entry(client, auth_headers, monkeypatch):
    # patch app.utils.http.post_json to return a canned success dict
    client.post("/diagnostics/webhook-test", headers=auth_headers,
                data={"csrf_token": _csrf(), "url": "http://example.com", "payload": "{}"})
    resp = client.get("/diagnostics", headers=auth_headers)
    assert b"manual_test" in resp.content or b"example.com" in resp.content

def test_webhook_replay_requires_auth(client):
    resp = client.post("/diagnostics/webhook-log/abc123/replay", data={"csrf_token": "x"}, follow_redirects=False)
    assert resp.status_code == 401

def test_webhook_replay_unknown_id_redirects(client, auth_headers):
    resp = client.post("/diagnostics/webhook-log/doesnotexist/replay",
                        headers=auth_headers, data={"csrf_token": _csrf()}, follow_redirects=False)
    assert resp.status_code == 303

def test_webhook_replay_sends_and_logs(client, auth_headers, monkeypatch):
    # seed a webhook_log entry directly via webhook_log.log_delivery(...), then POST replay,
    # patch app.utils.http.post_json, assert a new "replay"-sourced entry appears
    ...
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement** — add `import app.utils.http as http_util` to `diagnostics.py`; replace `test_webhook`'s inline urllib block with `http_util.post_json(url, payload)`, then `webhook_log.log_delivery("manual_test", url, payload, result.get("status"), result.get("error"))`; add `webhook_log_entries` to both `diagnostics_index` and `test_webhook`'s template context. Add:

```python
@router.post("/diagnostics/webhook-log/{entry_id}/replay", dependencies=[Depends(requires_admin)])
async def replay_webhook(request: Request, entry_id: str, csrf_token: str = Form(...)):
```

Looks up the entry via `webhook_log.get_entry`; redirects to `/diagnostics` (303) if missing; otherwise calls `http_util.post_json(entry["url"], entry["payload"])`, logs it with source `"replay"`, then redirects to `/diagnostics` (303).

- [ ] **Step 4: Update the template** — add a "Webhook Delivery Log" card to `app/templates/diagnostics/index.html.j2` with a table (Time, Source, URL, Status, truncated Payload) iterating `webhook_log_entries`, each row ending in a small form (`hx-post` or plain `<form method="post">`) to `/diagnostics/webhook-log/{{ entry.id }}/replay` with the CSRF token, respecting `{% if not is_readonly() %}` like other mutating controls in this app.

- [ ] **Step 5: Run tests, confirm they pass** — `pytest tests/test_diagnostics.py -v`.

- [ ] **Step 6: Commit** — `git add app/routes/diagnostics.py app/templates/diagnostics/index.html.j2 tests/test_diagnostics.py && git commit -m "feat: add webhook delivery log view and replay"`
