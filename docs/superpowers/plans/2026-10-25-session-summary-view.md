# Session Summary View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A readable, non-AI "what happened in this room" report — participant join/leave timeline, track mute/unmute events, notes/tags, and any recordings — reachable both for a live room and for one that has just ended.

**Architecture correction, made during planning, not during the original scoping conversation:** this plan was originally going to read its timeline from `diagnostics.py`'s existing `room_support_bundle` (`build_timeline()` in `app/services/room_annotations.py`). Investigating that function while writing this plan found it only **synthesizes a timeline from the room's current live snapshot** (currently-connected participants' `joined_at`, current track state) — it has no memory of anyone who already left. For an ended room (the main case this feature exists for, per "reachable ... from ghost room entries after a room has ended"), every participant has by definition already left, so that existing function would always render an empty timeline. There is no persisted historical event log for a room anywhere in this codebase today (`events.py`'s SSE generator diffs live state but only streams it to a connected browser; nothing is stored). Making this feature actually show something for an ended room therefore requires a small independent background poller that records room lifecycle events as they happen, regardless of whether anyone has a page open — this is new, not a reuse of existing data as originally described. This is flagged here because it's a materially bigger piece of work than the other six plans in this series, not a trivial detail; the decision to build it anyway (rather than ship a feature that's empty for its main use case) is the plan author's call.

**Architecture:** A new background poller (`room_poller.py`), modeled on the polling/diffing already written in `app/routes/events.py`'s SSE generator but running independently as an `asyncio` task started at app startup (same pattern as the report-rules scheduler), ticks every 5 seconds (matching `events.py`'s existing `_POLL_INTERVAL`), diffs current LiveKit state against its own last-known state, and (a) calls the existing `ghost_rooms.record_poll()` from the ghost-rooms plan — making ghost detection reliable independent of someone viewing `/rooms`, fixing that plan's known limitation as a side effect — and (b) appends lifecycle events (room created, participant joined/left, track muted/unmuted) to a new per-room history store, `room_history.py`. A new `/rooms/{room_name}/summary` page renders that history plus existing annotations (notes/tags) plus that room's egress/recording jobs (queryable directly from LiveKit by room name even after the room ends — this part *is* real, existing capability: `LiveKitClient.list_egress(room_name=...)`).

**Tech Stack:** No new dependency.

**Spec:** No separate spec document — the user opted out of the brainstorming conversation for this work. Two scope corrections made here, not asked: (1) the AI-sentiment part of the original reference feature is dropped (no transcript/LLM pipeline in this app, as already flagged before planning began); (2) "alerts that fired during the session," also originally scoped in, is dropped here as not feasible — this app's alert rules (`app/services/alerts.py`) evaluate global dashboard-wide metrics (e.g. `rooms_total > 50`), not per-room conditions, so there is no concept of "an alert that fired for this specific room" to show.

**Depends on:** `docs/superpowers/plans/2026-10-25-ghost-rooms.md` (`ghost_rooms.record_poll`, `TTL_MINUTES`) — build that plan first.

## Global Constraints

- No new dependency.
- The poller must run exactly once per tick regardless of how many browser tabs are open or closed — it is independent of any request or SSE connection, unlike `events.py`'s existing per-connection poller.
- A session summary's event history is retained for the same `TTL_MINUTES` window as its ghost-room row (imported from `ghost_rooms.py`, not re-declared, so the two can never drift out of sync) — a summary page for a room older than that window shows "no longer available" rather than a stale or empty report that looks like a real (but uneventful) session.
- The poller's per-tick work must be wrapped so one room's failure (e.g., `list_participants` raising for a room that vanished mid-tick) cannot stop the tick from processing other rooms or from running again next cycle.

## Review Focus

- A room with zero participants ever joining (created and immediately left empty, or a metadata-only room) must render a summary with "Room created" and nothing else, not an empty page or an error.
- A participant who joins and leaves entirely between two 5-second poll ticks is, like the unobserved-room case already documented in the ghost-rooms plan, simply never recorded — this is an accepted limitation of poll-based detection at this interval, not a bug to chase in this plan.
- Requesting a summary for a room name that was never seen by the poller and isn't currently live must render a clear "no data" state, not a 500 from an empty/missing history lookup.
- `lk.list_egress(room_name=...)` failing (e.g., LiveKit temporarily unreachable) must degrade the summary page to "recording info unavailable," not fail the whole page render — mirrors the existing try/except-and-continue pattern already used in `diagnostics.py`'s `room_support_bundle`.
- Two participants joining in the same poll tick must both be recorded as separate `participant_joined` events (not deduplicated or collapsed into one), since the diff is a set difference over all newly-present identities, not a single "something changed" flag.

---

## File Structure

- Create `app/services/room_history.py` — per-room event log store + the pure diff function.
- Create `app/services/room_poller.py` — the background poll loop that calls both `ghost_rooms.record_poll` and `room_history`'s diff/append.
- Modify `app/main.py` — start/stop the poller task in `lifespan`.
- Modify `app/routes/rooms.py` — new `/rooms/{room_name}/summary` route.
- Create `app/templates/rooms/summary.html.j2`.
- Modify `app/templates/rooms/detail.html.j2` — add a link to the summary.
- Modify `app/templates/rooms/_rooms_table.html.j2` — make the ghost row's "Ended Xm ago" badge a link to the summary (upgrading the plain-text badge the ghost-rooms plan shipped).
- Tests: `tests/test_room_history.py`, `tests/test_room_poller.py`, extend `tests/test_rooms.py`.

### Task 1: Room history store and the pure diff function

**Files:**
- Create: `app/services/room_history.py`
- Test: `tests/test_room_history.py`

**Interfaces:**
- Consumes: `app.services.ghost_rooms.TTL_MINUTES` (ghost-rooms plan).
- Produces:

```python
def append_event(room_name: str, kind: str, label: str, identity: str = "") -> None: ...
def get_history(room_name: str) -> list[dict]: ...   # chronological, oldest first; [] if unknown/expired
def prune_old(now: datetime) -> None: ...             # drops rooms whose last event predates TTL_MINUTES

def diff_room_state(prev: dict | None, curr: dict) -> tuple[list[dict], dict]: ...
```

`curr` (and `prev`, when not `None`) are shaped `{"participants": {identity: {"muted_tracks": set[str]}}}`. `diff_room_state` returns `(events, new_state)` where `events` is a list of `{"kind": str, "label": str, "identity": str}` dicts (no `ts` — the caller timestamps on append) for: `"participant_joined"` (identity in `curr` not in `prev`), `"participant_left"` (identity in `prev` not in `curr`), `"track_muted"` / `"track_unmuted"` (a track sid present in one side's `muted_tracks` set but not the other, for identities present in both). `prev=None` means "room not seen before" — no join/leave events are synthesized for a never-before-seen room's *existing* participants (they joined before this poller started watching; only a `"room_created"` event, handled by the caller, applies), only the raw state is returned as `new_state` for next time's diff.

- [ ] **Step 1: Write failing tests**

```python
def test_diff_first_sighting_produces_no_events():
    events, state = rh.diff_room_state(None, {"participants": {"a": {"muted_tracks": set()}}})
    assert events == []
    assert state == {"participants": {"a": {"muted_tracks": set()}}}

def test_diff_detects_join_and_leave():
    prev = {"participants": {"a": {"muted_tracks": set()}}}
    curr = {"participants": {"b": {"muted_tracks": set()}}}
    events, _ = rh.diff_room_state(prev, curr)
    kinds_identities = {(e["kind"], e["identity"]) for e in events}
    assert ("participant_left", "a") in kinds_identities
    assert ("participant_joined", "b") in kinds_identities

def test_diff_detects_mute_and_unmute():
    prev = {"participants": {"a": {"muted_tracks": set()}}}
    curr = {"participants": {"a": {"muted_tracks": {"track1"}}}}
    events, _ = rh.diff_room_state(prev, curr)
    assert any(e["kind"] == "track_muted" and e["identity"] == "a" for e in events)

    events2, _ = rh.diff_room_state(curr, prev)
    assert any(e["kind"] == "track_unmuted" and e["identity"] == "a" for e in events2)

def test_append_and_get_history_chronological(tmp_path):
    with patch.object(rh, "_STORE_PATH", str(tmp_path / "h.json")):
        rh.append_event("r1", "room_created", "Room created")
        rh.append_event("r1", "participant_joined", "alice joined", identity="alice")
        history = rh.get_history("r1")
    assert [e["kind"] for e in history] == ["room_created", "participant_joined"]

def test_get_history_unknown_room_empty(tmp_path):
    with patch.object(rh, "_STORE_PATH", str(tmp_path / "h.json")):
        assert rh.get_history("nope") == []

def test_prune_old_drops_stale_rooms(tmp_path):
    with patch.object(rh, "_STORE_PATH", str(tmp_path / "h.json")):
        rh.append_event("r1", "room_created", "Room created")
        old_entries = rh.get_history("r1")
        # manually age the file's last event by writing an old ts, then prune
        ...
        rh.prune_old(datetime.now(timezone.utc))
        assert rh.get_history("r1") == []
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement.** `_STORE_PATH` from env var `ROOM_HISTORY_FILE`, default `/tmp/room_history.json`, shape `{room_name: [{"ts": iso, "kind": str, "label": str, "identity": str}]}`. `append_event` loads, appends with `"ts": datetime.now(timezone.utc).isoformat(...)`, saves (no need for a `MAX_ENTRIES`-per-room cap given `prune_old` already bounds total retention by time, but cap each room's own event list at a generous `MAX_EVENTS_PER_ROOM = 500` defensively, same spirit as `audit_log.py`'s trim). `prune_old` drops any `room_name` key whose last event's `ts` is older than `TTL_MINUTES` (imported from `app.services.ghost_rooms`).

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Commit** — `git add app/services/room_history.py tests/test_room_history.py && git commit -m "feat: add room lifecycle history store and diff logic"`

### Task 2: Background poller

**Files:**
- Create: `app/services/room_poller.py`
- Modify: `app/main.py` (`lifespan`)
- Test: `tests/test_room_poller.py`, extend `tests/test_main.py`

**Interfaces:**
- Consumes: `room_history.diff_room_state`, `room_history.append_event`, `room_history.prune_old` (Task 1); `ghost_rooms.record_poll` (ghost-rooms plan).
- Produces: `async def poll_once(lk: LiveKitClient) -> None`, `async def run_poller_loop(interval_seconds: int = 5) -> None`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_poll_once_records_room_created_on_first_sighting(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(gr, "_STORE_PATH", str(tmp_path / "g.json"))
    rp._reset_for_tests()  # clears the module's in-memory last-known-state dict
    lk = MagicMock()
    lk.list_rooms = AsyncMock(return_value=([SimpleNamespace(name="r1", num_participants=0, max_participants=10, creation_time=1, metadata="")], 0.01))
    lk.list_participants = AsyncMock(return_value=[])
    await rp.poll_once(lk)
    assert any(e["kind"] == "room_created" for e in rh.get_history("r1"))

@pytest.mark.asyncio
async def test_poll_once_records_join_across_two_ticks(tmp_path, monkeypatch):
    # first tick: room with no participants; second tick: same room with participant "alice"
    # assert rh.get_history("r1") contains a participant_joined event for alice after the second tick

@pytest.mark.asyncio
async def test_poll_once_continues_after_one_room_errors(tmp_path, monkeypatch):
    # list_participants raises for room "bad" but returns fine for room "good"; assert "good" still gets recorded
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement.** Module-level `_last_known: dict[str, dict] = {}` (same precedent as `app/services/cache.py`'s module-level store), plus a `_reset_for_tests()` helper. `poll_once`: `rooms, _ = await lk.list_rooms()`; build the ghost-rooms snapshot list exactly as `rooms.py`'s route does and call `ghost_rooms.record_poll(snapshot)`; for each room, wrap in `try/except Exception: continue`, fetch `participants = await lk.list_participants(room.name)`, build `curr_state = {"participants": {p.identity: {"muted_tracks": {t.sid for t in p.tracks if getattr(t, "muted", False)}} for p in participants}}`, look up `prev_state = _last_known.get(room.name)`; if `prev_state is None`: `room_history.append_event(room.name, "room_created", "Room created")`; `events, new_state = room_history.diff_room_state(prev_state, curr_state)`; for each event, `room_history.append_event(room.name, event["kind"], <human label built from kind+identity>, identity=event["identity"])`; set `_last_known[room.name] = new_state`. After the loop, also detect rooms present in `_last_known` but absent from current `rooms` and remove them from `_last_known` (so a room that comes back later is treated as a fresh sighting, consistent with ghost-rooms treating a same-named recreated room as live again) — do **not** synthesize a `"room_ended"` event for this (the ghost-rooms row already communicates that visually; avoid a duplicate signal two different stores both try to own). Finally call `room_history.prune_old(datetime.now(timezone.utc))`. `run_poller_loop`: `while True: try: await poll_once(LiveKitClient()) except Exception: pass; await asyncio.sleep(interval_seconds)`.

- [ ] **Step 4: Run tests, confirm they pass.**

- [ ] **Step 5: Wire into `app/main.py`'s `lifespan`**, alongside the report-rules scheduler task from the scheduled-report-rules plan (both are independent `asyncio.create_task`s started at startup and cancelled at shutdown).

- [ ] **Step 6: Run the full test suite** (`pytest tests/ -v`) to confirm two background tasks now starting/stopping per test via the `client` fixture doesn't introduce flakiness or hangs.

- [ ] **Step 7: Commit** — `git add app/services/room_poller.py app/main.py tests/ && git commit -m "feat: run independent room lifecycle poller"`

### Task 3: Session summary page

**Files:**
- Modify: `app/routes/rooms.py` (new route)
- Create: `app/templates/rooms/summary.html.j2`
- Modify: `app/templates/rooms/detail.html.j2` (link to summary)
- Modify: `app/templates/rooms/_rooms_table.html.j2` (ghost badge becomes a link)
- Test: extend `tests/test_rooms.py`

**Interfaces:**
- Consumes: `room_history.get_history` (Task 1), `annotations.get_annotations`, `lk.list_egress(room_name, active=False)` (existing, `app/services/livekit.py:233`).
- Produces: `GET /rooms/{room_name}/summary` (admin-protected).

- [ ] **Step 1: Write failing tests**

```python
def test_summary_requires_auth(client):
    resp = client.get("/rooms/r1/summary", follow_redirects=False)
    assert resp.status_code == 401

def test_summary_shows_history_and_notes(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    rh.append_event("r1", "room_created", "Room created")
    rh.append_event("r1", "participant_joined", "alice joined", identity="alice")
    resp = client.get("/rooms/r1/summary", headers=auth_headers)
    assert resp.status_code == 200
    assert b"alice joined" in resp.content

def test_summary_unknown_room_shows_no_data_state(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "h.json"))
    resp = client.get("/rooms/never-seen/summary", headers=auth_headers)
    assert resp.status_code == 200
    assert b"No data" in resp.content or b"no history" in resp.content.lower()

def test_summary_degrades_when_egress_lookup_fails(client, auth_headers, tmp_path, monkeypatch):
    # patch lk.list_egress to raise; page must still render 200 with a fallback message
```

- [ ] **Step 2: Run tests, confirm they fail.**

- [ ] **Step 3: Implement the route.**

```python
@router.get("/rooms/{room_name}/summary", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def room_summary(request: Request, room_name: str, lk: LiveKitClient = Depends(get_livekit_client)):
```

`history = room_history.get_history(room_name)`; `room_notes = annotations.get_annotations(room_name)`; try `egress_jobs = await lk.list_egress(room_name=room_name, active=False)` except Exception → `egress_jobs = None` (template shows "recording info unavailable" when `None`, vs. an empty list meaning "no recordings"). Render `rooms/summary.html.j2` with `history`, `room_notes`, `egress_jobs`, `room_name`.

- [ ] **Step 4: Implement the template** — a timeline list from `history` (icon/label/timestamp per existing `build_timeline` event rendering conventions already used in `rooms/detail.html.j2`, for visual consistency), a notes/tags block from `room_notes`, an egress/recordings table (or the unavailable/empty states), and a "No data available for this room" empty state when `history` is `[]`.

- [ ] **Step 5: Add the link** — in `rooms/detail.html.j2`, a "View Session Summary" button pointing to `/rooms/{{ room.name }}/summary`. In `_rooms_table.html.j2`'s ghost row (added by the ghost-rooms plan), change the plain-text "Ended {{ room._closed_minutes_ago }}m ago" into `<a href="/rooms/{{ room.name }}/summary">Ended {{ room._closed_minutes_ago }}m ago — View Summary</a>`.

- [ ] **Step 6: Run tests, confirm they pass.**

- [ ] **Step 7: Commit** — `git add app/routes/rooms.py app/templates/rooms/summary.html.j2 app/templates/rooms/detail.html.j2 app/templates/rooms/_rooms_table.html.j2 tests/test_rooms.py && git commit -m "feat: add session summary page for live and recently-ended rooms"`
