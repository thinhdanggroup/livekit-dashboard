# Security Visibility (Failed Logins + IP Allowlist) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the operator visibility into failed login attempts by source IP, and an optional IP allowlist, as a scoped-down stand-in for the reference product's fail2ban integration (which assumes a host-level fail2ban process this dashboard does not run and cannot assume exists).

**Architecture:** `app/security/basic_auth.py`'s `requires_admin` dependency gains a `Request` parameter and logs every failed credential check (IP + username tried) to a new append-only store, `security_log.py`, following the existing `audit_log.py` pattern. A new `ip_allowlist.py` service holds an optional comma-separated allowlist (empty = allow all, the default). A new `app.middleware("http")` in `main.py`, modeled on the existing `enforce_readonly_mode` middleware, rejects requests from IPs not on the list when the list is non-empty. Both surface in a new "Security" card on the existing `settings.html.j2` page.

**Tech Stack:** No new dependency.

**Spec:** No separate spec document — the user opted out of the brainstorming conversation for this work. One consequential scope decision made here without asking: this intentionally does **not** auto-ban IPs (no fail2ban-style enforcement based on attempt count) — it only logs attempts and offers an opt-in allowlist, because auto-banning in a single-shared-credential app (no per-user accounts) risks the operator locking themselves out with no recovery path other than server filesystem access. This is recorded here as the plan author's call, not the user's.

## Global Constraints

- No new dependency.
- Follow the existing JSON-file append-only store pattern (`app/services/audit_log.py`) for the failed-login log, and the existing single-JSON-config pattern (`app/services/notifications.py`) for the allowlist.
- The IP allowlist must default to empty (allow all) on a fresh install — this is a safety requirement, not a preference: an allowlist that defaults to "deny all" or requires explicit setup before the dashboard is reachable would lock every new install out immediately.
- Saving a non-empty allowlist must always include the IP making that save request, even if the operator didn't type it — otherwise submitting the allowlist form is itself a self-lockout. This is a deliberate safety net, implemented in `ip_allowlist.save_allowlist`, not left to the UI or the operator to remember.
- `/health` is exempt from the IP allowlist (matches `enforce_readonly_mode`'s existing exemption pattern for `/auth`), since it is commonly probed by infrastructure (load balancers, container orchestrators) from IPs the operator may not think to allowlist.

## Review Focus

- Saving an allowlist of `"203.0.113.5"` from a browser at `198.51.100.9` must result in a stored list containing **both** IPs (the safety net above), not just the one typed — a plan that only stores what was typed would lock the operator out on their very next request.
- An empty submitted allowlist must clear back to allow-all, not append the requester's IP into a single-entry "allowlist" that then effectively blocks everyone else for an operator who meant "turn this off."
- `request.client` can be `None` in some ASGI test/proxy contexts — the failed-login logger and the allowlist check must handle that without raising (log/allow with a placeholder like `"unknown"` rather than crashing the auth flow).
- A successful login must never be logged as a failed attempt, and a failed attempt must never raise anything other than the existing 401 — logging failures must not change the auth endpoint's external behavior or status code.
- The allowlist middleware must run before `requires_admin` can even prompt for credentials (i.e., as request middleware, not inside the auth dependency) so a blocked IP gets a flat 403 without a basic-auth challenge leaking which paths exist.

---

## File Structure

- Create `app/services/security_log.py` — failed-login append-only log.
- Create `app/services/ip_allowlist.py` — allowlist config store + check.
- Modify `app/security/basic_auth.py` — log failed attempts.
- Modify `app/main.py` — add the allowlist-enforcing middleware.
- Modify `app/routes/settings.py` — expose log/allowlist data, add save route.
- Modify `app/templates/settings.html.j2` — add the Security card.
- Tests: `tests/test_security_log.py`, `tests/test_ip_allowlist.py`, extend `tests/test_security.py` and relevant settings/main tests.

### Task 1: Failed-login log store

**Files:**
- Create: `app/services/security_log.py`
- Test: `tests/test_security_log.py`

**Interfaces:**
- Produces:
  - `log_failed_login(ip: str, username: str) -> None`
  - `list_failed_logins(limit: int = 100) -> list[dict]` — newest-first, entries shaped `{"ts": iso-str, "ip": str, "username": str}`.
  - `count_by_ip(limit: int = 500) -> dict[str, int]` — counts failed attempts per IP over the most recent `limit` entries, descending by count.
- `_STORE_PATH` from env var `SECURITY_LOG_FILE`, default `/tmp/security_log.json`. `MAX_ENTRIES = 500` (matches `audit_log.py`).

- [ ] **Step 1: Write failing tests**

```python
def test_list_failed_logins_empty(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        assert sl.list_failed_logins() == []

def test_log_failed_login_persists_newest_first(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("2.2.2.2", "root")
        entries = sl.list_failed_logins()
    assert entries[0]["ip"] == "2.2.2.2"
    assert entries[1]["ip"] == "1.1.1.1"

def test_count_by_ip_groups_and_sorts(tmp_path):
    with patch.object(sl, "_STORE_PATH", str(tmp_path / "s.json")):
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("1.1.1.1", "admin")
        sl.log_failed_login("2.2.2.2", "root")
        counts = sl.count_by_ip()
    assert counts["1.1.1.1"] == 2
    assert counts["2.2.2.2"] == 1
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement**, mirroring `app/services/audit_log.py`'s structure exactly.

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/security_log.py tests/test_security_log.py && git commit -m "feat: add failed-login log store"`

### Task 2: IP allowlist store

**Files:**
- Create: `app/services/ip_allowlist.py`
- Test: `tests/test_ip_allowlist.py`

**Interfaces:**
- Produces:
  - `get_allowlist() -> list[str]` — empty list means allow all.
  - `save_allowlist(raw: str, requester_ip: str) -> list[str]` — parses `raw` as a comma-separated list, strips whitespace and drops blanks/dupes; if the resulting list is non-empty and `requester_ip` is not already in it, appends `requester_ip`; if `raw` is blank/whitespace-only, saves and returns an empty list (allow-all) regardless of `requester_ip`. Persists and returns the final stored list.
  - `is_allowed(ip: str) -> bool` — `True` if the stored list is empty, or `ip in` the stored list.
- `_STORE_PATH` from env var `IP_ALLOWLIST_FILE`, default `/tmp/ip_allowlist.json`. Store shape: `{"ips": [...]}`.

- [ ] **Step 1: Write failing tests**

```python
def test_get_allowlist_defaults_empty(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        assert ipa.get_allowlist() == []

def test_is_allowed_true_when_list_empty(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        assert ipa.is_allowed("9.9.9.9") is True

def test_save_allowlist_includes_requester_ip(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        result = ipa.save_allowlist("203.0.113.5", requester_ip="198.51.100.9")
    assert "203.0.113.5" in result
    assert "198.51.100.9" in result

def test_save_blank_allowlist_clears_to_allow_all(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        ipa.save_allowlist("203.0.113.5", requester_ip="198.51.100.9")
        result = ipa.save_allowlist("", requester_ip="198.51.100.9")
    assert result == []
    assert ipa.is_allowed("9.9.9.9") is True

def test_is_allowed_checks_membership_after_save(tmp_path):
    with patch.object(ipa, "_STORE_PATH", str(tmp_path / "a.json")):
        ipa.save_allowlist("203.0.113.5", requester_ip="203.0.113.5")
    assert ipa.is_allowed("203.0.113.5") is True
    assert ipa.is_allowed("9.9.9.9") is False
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/ip_allowlist.py tests/test_ip_allowlist.py && git commit -m "feat: add IP allowlist store"`

### Task 3: Log failed logins from `requires_admin`

**Files:**
- Modify: `app/security/basic_auth.py:30-38`
- Test: extend `tests/test_security.py`

**Interfaces:**
- Consumes: `security_log.log_failed_login(ip: str, username: str) -> None` (Task 1).
- Produces: `requires_admin`'s signature becomes `requires_admin(request: Request, credentials: HTTPBasicCredentials = Depends(security)) -> str` — its behavior (return value on success, `HTTPException(401)` on failure) is otherwise unchanged, so every existing route using `Depends(requires_admin)` keeps working without modification.

- [ ] **Step 1: Write failing test**

```python
def test_requires_admin_logs_failed_attempt(client, tmp_path, monkeypatch):
    import app.services.security_log as sl
    monkeypatch.setattr(sl, "_STORE_PATH", str(tmp_path / "s.json"))
    import base64
    bad = base64.b64encode(b"wrong:wrong").decode()
    client.get("/rooms", headers={"Authorization": f"Basic {bad}"})
    entries = sl.list_failed_logins()
    assert len(entries) == 1
    assert entries[0]["username"] == "wrong"

def test_requires_admin_does_not_log_success(client, auth_headers, tmp_path, monkeypatch):
    import app.services.security_log as sl
    monkeypatch.setattr(sl, "_STORE_PATH", str(tmp_path / "s.json"))
    client.get("/rooms", headers=auth_headers)
    assert sl.list_failed_logins() == []
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement.** Add `request: Request` as `requires_admin`'s first parameter (FastAPI injects it automatically; no `Depends()` needed for `Request` itself). In the `if not verify_credentials(credentials):` branch, before raising, call `security_log.log_failed_login(request.client.host if request.client else "unknown", credentials.username)`.

- [ ] **Step 4: Run tests, confirm they pass** — also run `pytest tests/ -k requires_admin -v` and the broader suite once to confirm no route's `Depends(requires_admin)` usage broke from the signature change.

- [ ] **Step 5: Commit** — `git add app/security/basic_auth.py tests/test_security.py && git commit -m "feat: log failed login attempts by IP"`

### Task 4: Enforce the allowlist and wire up the Settings UI

**Files:**
- Modify: `app/main.py` (new middleware, alongside `enforce_readonly_mode`)
- Modify: `app/routes/settings.py`
- Modify: `app/templates/settings.html.j2`
- Test: extend whichever test file covers `settings.py` routes (check for `tests/test_settings.py`; if none exists, add assertions to `tests/test_security.py` or create `tests/test_settings.py` following the same route-test pattern as `tests/test_diagnostics.py`)

**Interfaces:**
- Consumes: `ip_allowlist.is_allowed`, `ip_allowlist.get_allowlist`, `ip_allowlist.save_allowlist` (Task 2); `security_log.list_failed_logins`, `security_log.count_by_ip` (Task 1).
- Produces: new route `POST /settings/security`; `settings_index`'s template context gains `failed_logins`, `failed_login_counts`, `ip_allowlist_raw`.

- [ ] **Step 1: Write failing tests**

```python
def test_blocked_ip_gets_403(client, tmp_path, monkeypatch):
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    ipa.save_allowlist("203.0.113.5", requester_ip="203.0.113.5")  # testclient's IP is not this
    resp = client.get("/health")  # exempt path still works
    assert resp.status_code == 200
    resp2 = client.get("/rooms")
    assert resp2.status_code == 403

def test_allowlisted_ip_passes(client, tmp_path, monkeypatch, auth_headers):
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    # TestClient's default client host is "testclient" — allowlist it explicitly
    ipa.save_allowlist("testclient", requester_ip="testclient")
    resp = client.get("/rooms", headers=auth_headers)
    assert resp.status_code == 200

def test_settings_page_shows_failed_logins_and_allowlist_form(client, auth_headers, tmp_path, monkeypatch):
    import app.services.security_log as sl
    monkeypatch.setattr(sl, "_STORE_PATH", str(tmp_path / "s.json"))
    sl.log_failed_login("9.9.9.9", "admin")
    resp = client.get("/settings", headers=auth_headers)
    assert b"9.9.9.9" in resp.content

def test_save_security_settings_updates_allowlist(client, auth_headers, tmp_path, monkeypatch):
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    resp = client.post("/settings/security", headers=auth_headers,
                        data={"csrf_token": _csrf(), "ip_allowlist": "203.0.113.5"},
                        follow_redirects=False)
    assert resp.status_code == 303
    assert "203.0.113.5" in ipa.get_allowlist()
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement the middleware** in `app/main.py`, placed before `enforce_readonly_mode` (order doesn't functionally matter here since they check different things, but a 403 for IP should short-circuit before any mutation check runs):

```python
@app.middleware("http")
async def enforce_ip_allowlist(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    if not ip_allowlist.is_allowed(client_ip):
        from fastapi.responses import Response as _Resp
        return _Resp("Access denied.", status_code=403)
    return await call_next(request)
```

- [ ] **Step 4: Implement the settings route and view.** In `settings.py`, add to `settings_index`'s template context: `"failed_logins": security_log.list_failed_logins(limit=20)`, `"failed_login_counts": security_log.count_by_ip()`, `"ip_allowlist_raw": ", ".join(ip_allowlist.get_allowlist())`. Add:

```python
@router.post("/settings/security", dependencies=[Depends(requires_admin)])
async def save_security_settings(request: Request, csrf_token: str = Form(...), ip_allowlist: str = Form("")):
```

verifies CSRF, calls `ip_allowlist_service.save_allowlist(ip_allowlist, requester_ip=request.client.host if request.client else "unknown")` (import the module under an alias to avoid shadowing the `ip_allowlist` form parameter name), redirects to `/settings` (303).

- [ ] **Step 5: Add the Security card to `settings.html.j2`** — a table of `failed_login_counts` (IP, count) and the 20 most recent `failed_logins` (time, IP, username tried), plus a form posting to `/settings/security` with a text input pre-filled from `ip_allowlist_raw` and helper text: "Leave blank to allow all IPs. Your current IP is always kept on the list when you save a non-empty allowlist." Respect `{% if not is_readonly() %}` around the form, matching other mutating controls.

- [ ] **Step 6: Run tests, confirm they pass**, and run the full suite once (`pytest tests/ -v`) to confirm the new allowlist middleware doesn't break any existing test that doesn't pass `auth_headers`/isn't aware of client IPs (the default allow-all behavior should make this a no-op for every pre-existing test).

- [ ] **Step 7: Commit** — `git add app/main.py app/routes/settings.py app/templates/settings.html.j2 tests/ && git commit -m "feat: add IP allowlist enforcement and security settings UI"`
