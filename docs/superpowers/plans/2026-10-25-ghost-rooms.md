# Ghost Rooms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep a room visible in the `/rooms` list for a short window after it ends, badged as ended, so an operator debugging "where did that room go" doesn't have to catch it live.

**Architecture:** LiveKit's `list_rooms()` only returns currently-live rooms, so ended rooms vanish instantly today. A new JSON-file store (`ghost_rooms.py`) remembers the last-seen set of live room names; each time `/rooms` loads, it diffs the new live set against the remembered one, demotes any room that disappeared into a time-stamped "ghost" entry, prunes ghosts older than a fixed TTL, and the route merges ghosts into the rendered list as read-only rows.

**Tech Stack:** No new dependency. Same JSON-file store pattern as `app/services/audit_log.py`.

**Spec:** No separate spec document — the user opted out of the brainstorming conversation for this work; scope and rationale are recorded in this plan and the originating conversation.

## Global Constraints

- No new dependency.
- Follow the existing `_load`/`_save` JSON-file store pattern (env-var configurable path).
- Ghost rows must never expose mutating controls (edit/delete/kick) — the room no longer exists on the LiveKit server, so those actions would silently fail or 404 against the real API.
- This feature only runs on the existing `/rooms` GET path; it must not add a new background poller or change `/rooms`'s response time meaningfully (the diff is an in-memory set comparison plus one small file write).

## Review Focus

- A room that was never seen as live by this dashboard (e.g., it started and ended between two page loads with nobody visiting `/rooms` in between) is never shown as a ghost — document this as expected (detection only catches transitions this dashboard actually observed), not a bug to chase.
- Two different rooms that happen to share a name across the TTL window (one ends, a new one with the same name is created) must not show stale ghost data overwriting or confusing the live entry — the live entry always wins; a name present in the current live set is never also rendered as a ghost even if a stale ghost record exists for it.
- Ghost entries older than the TTL must be pruned from the store itself (not just hidden in rendering), so the file doesn't grow unbounded over a long-running server.
- The HTMX partial (`_rooms_table.html.j2`) must render correctly with zero ghosts, some ghosts, and only ghosts (no live rooms) — the existing empty-state branch must not fire just because live rooms are empty if ghosts exist.
- Search filtering (`?search=`) on `/rooms` must apply to ghost names the same way it applies to live room names, so a search doesn't leak unrelated ghosts into the result.

---

## File Structure

- Create `app/services/ghost_rooms.py` — tracks the live-room snapshot and ghost entries.
- Modify `app/routes/rooms.py` — call the tracker on every `/rooms` load, wrap ghosts for template rendering, merge into the list, set `_ghost`/`_closed_minutes_ago` on the existing `_RoomView` wrapper.
- Modify `app/templates/rooms/_rooms_table.html.j2` — render ghost rows distinctly, no action buttons.
- Tests: `tests/test_ghost_rooms.py`, extend `tests/test_rooms.py`.

### Task 1: Ghost room tracker service

**Files:**
- Create: `app/services/ghost_rooms.py`
- Test: `tests/test_ghost_rooms.py`

**Interfaces:**
- Produces:
  - `record_poll(live_rooms: list[dict]) -> list[dict]` — `live_rooms` is a list of plain dicts `{"name": str, "num_participants": int, "max_participants": int, "creation_time": int, "metadata": str}`. Diffs against the stored "last known live" set; any previously-known-live name missing from `live_rooms` becomes a new ghost entry with `closed_at` = now (UTC ISO). Updates the stored live set to exactly the names in `live_rooms`. Prunes ghosts whose `closed_at` is older than `TTL_MINUTES`. Persists. Returns the current (post-prune) list of ghost entries, newest-first, each shaped `{"name": str, "max_participants": int, "creation_time": int, "metadata": str, "closed_at": iso-str, "closed_minutes_ago": int}`.
  - `TTL_MINUTES: int = 15` (module-level constant).
- `_STORE_PATH` from env var `GHOST_ROOMS_FILE`, default `/tmp/ghost_rooms.json`. Store shape on disk: `{"live": {name: snapshot}, "ghosts": {name: {...snapshot, "closed_at": iso}}}`.

- [ ] **Step 1: Write failing tests**

```python
def test_record_poll_no_change_returns_no_ghosts(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
        ghosts = gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
    assert ghosts == []

def test_room_disappearing_becomes_ghost(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": "m"}])
        ghosts = gr.record_poll([])  # r1 is gone
    assert len(ghosts) == 1
    assert ghosts[0]["name"] == "r1"
    assert ghosts[0]["closed_minutes_ago"] == 0

def test_room_recreated_is_not_a_ghost(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
        gr.record_poll([])  # r1 ends -> ghost
        ghosts = gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 2, "metadata": ""}])  # r1 live again
    assert ghosts == []  # live entries are never also shown as ghosts

def test_ghosts_older_than_ttl_are_pruned(tmp_path):
    with patch.object(gr, "_STORE_PATH", str(tmp_path / "g.json")), patch.object(gr, "TTL_MINUTES", 0):
        gr.record_poll([{"name": "r1", "num_participants": 1, "max_participants": 10, "creation_time": 1, "metadata": ""}])
        gr.record_poll([])  # ghost created, immediately older than a 0-minute TTL
        ghosts = gr.record_poll([])  # next poll should prune it
    assert ghosts == []
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement** `app/services/ghost_rooms.py`. Compute `closed_minutes_ago` as `int((now - datetime.fromisoformat(closed_at)).total_seconds() // 60)` at read time (not stored, since it changes over time). On each call: (1) for every name now present in `live_rooms`, delete it from the stored `ghosts` dict if present — a room that's live again is never also a ghost, even if a stale ghost record exists for it; (2) for every name in the previously-stored `live` set that is absent from the new `live_rooms`, add it to `ghosts` with `closed_at = now`; (3) overwrite the stored `live` set with exactly the names in `live_rooms`; (4) prune any ghost whose age in minutes `>= TTL_MINUTES`; (5) save; (6) return the surviving ghosts, newest-`closed_at`-first.

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/ghost_rooms.py tests/test_ghost_rooms.py && git commit -m "feat: add ghost room tracker"`

### Task 2: Wire into `/rooms` and render

**Files:**
- Modify: `app/routes/rooms.py:23-84` (`rooms_index`, `_annotate`)
- Modify: `app/templates/rooms/_rooms_table.html.j2`
- Test: extend `tests/test_rooms.py`

**Interfaces:**
- Consumes: `ghost_rooms.record_poll(live_rooms: list[dict]) -> list[dict]` (Task 1).
- Produces: `_annotate(room)`'s returned `_RoomView` now also exposes `_ghost = False` and `_closed_minutes_ago = None` (so the template can branch on `room._ghost` uniformly for both live and ghost rows). A new `_GhostRoomView` class exposes `.name`, `.num_participants` (always `0`), `.max_participants`, `.creation_time`, `.empty_timeout` (always `0`), `.metadata`, `._pinned = False`, `._tags = []`, `._note = ""`, `._ghost = True`, `._closed_minutes_ago: int`.

- [ ] **Step 1: Write failing test**

```python
def test_rooms_index_shows_ghost_after_room_disappears(client, auth_headers, monkeypatch):
    import app.services.ghost_rooms as gr
    # first request: lk.list_rooms returns one room "r1"
    # second request: lk.list_rooms returns [] (r1 ended)
    # assert the second response contains "r1" and an "ended" badge text
```

(Mock `get_livekit_client` dependency override via `app.dependency_overrides`, matching whatever pattern `tests/test_rooms.py` already uses for `lk.list_rooms`.)

- [ ] **Step 2: Run test, confirm it fails.**

- [ ] **Step 3: Implement.** In `rooms_index`, after `rooms, latency = await lk.list_rooms()`, build `snapshot = [{"name": r.name, "num_participants": getattr(r, "num_participants", 0), "max_participants": getattr(r, "max_participants", 0), "creation_time": getattr(r, "creation_time", 0), "metadata": getattr(r, "metadata", "")} for r in rooms]` and call `ghosts = ghost_rooms.record_poll(snapshot)`. Apply the same `search` filter to `ghosts` (by `name`) as already applied to `rooms`. Set `v._ghost = False` and `v._closed_minutes_ago = None` inside `_annotate`. Build `ghost_views = [_GhostRoomView(**g) for g in ghosts]` and append them to `unpinned_rooms` before passing to `template_data["rooms"]`.

- [ ] **Step 4: Update the template.** In `app/templates/rooms/_rooms_table.html.j2`, wrap the Actions `<td>` in `{% if not room._ghost %}...{% else %}<span class="text-muted">Ended {{ room._closed_minutes_ago }}m ago</span>{% endif %}`, and give the participants-badge cell a ghost-specific muted badge ("Ended") instead of the live green/gray participant-count badge when `room._ghost` is true. Do not change the empty-state branch's condition beyond ensuring it only fires when both `rooms` (now ghost-inclusive) is empty — no change needed there since ghosts are already merged into `rooms` before the template renders.

- [ ] **Step 5: Run tests, confirm they pass** — `pytest tests/test_rooms.py -v`.

- [ ] **Step 6: Commit** — `git add app/routes/rooms.py app/templates/rooms/_rooms_table.html.j2 tests/test_rooms.py && git commit -m "feat: show recently-ended rooms as ghosts in the room list"`
