# Global Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/search?q=<term>` endpoint that searches across rooms, participants, egress jobs, and ingress streams, with a search bar in the base navigation.

**Architecture:** A new `app/services/search.py` fetches all four entity types concurrently via `asyncio.gather`, applies a case-insensitive substring match, and returns typed `SearchResult` items grouped by kind. The route at `app/routes/search.py` calls the service and renders `app/templates/search/results.html.j2`. A reusable `_search_bar.html.j2` partial is included in `base.html.j2`'s top bar so every page has a search input.

**Tech Stack:** FastAPI, Jinja2 SSR, HTMX, Bootstrap 5, pytest-asyncio, `unittest.mock.AsyncMock`

## Global Constraints

- Python ^3.11
- No new dependencies — only stdlib + existing packages
- All routes protected by `requires_admin` (HTTP Basic Auth)
- All API calls wrapped in try/except; partial failures return empty list for that entity type
- Empty `q` returns empty results immediately (no API calls)
- Test filenames: `test_*.py`; test functions: `test_*`; asyncio_mode=auto
- `status_color` Jinja2 filter registered in `app/main.py` as `"status_color"`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `app/services/search.py` | `SearchResult` dataclass + `search_all()` async function |
| Create | `app/routes/search.py` | `GET /search` endpoint |
| Create | `app/templates/search/results.html.j2` | Search results page extending `base.html.j2` |
| Create | `app/templates/partials/_search_bar.html.j2` | Reusable search input |
| Modify | `app/main.py:129` | Register `search.router` |
| Modify | `app/templates/base.html.j2:107-117` | Embed `_search_bar.html.j2` in top bar |
| Create | `tests/test_search.py` | Service + route tests |

---

## Task 1: Search Service

**Files:**
- Create: `app/services/search.py`
- Test: `tests/test_search.py` (service section)

**Interfaces:**
- Produces: `SearchResult(kind: str, title: str, subtitle: str, url: str, status: str)` dataclass
- Produces: `search_all(lk: LiveKitClient, q: str) -> list[SearchResult]` async function
- `kind` values: `"room"`, `"participant"`, `"egress"`, `"ingress"`

- [ ] **Step 1: Write failing tests for search_all**

Create `tests/test_search.py`:

```python
"""Tests for app.services.search"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.search import SearchResult, search_all


def _make_lk(**overrides):
    lk = MagicMock()
    lk.sip_enabled = False
    lk.list_rooms = AsyncMock(return_value=([], 0.01))
    lk.get_all_participants_across_rooms = AsyncMock(return_value=[])
    lk.list_egress = AsyncMock(return_value=[])
    lk.list_ingress = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(lk, k, v)
    return lk


async def test_search_empty_q_returns_no_results_and_no_api_calls():
    lk = _make_lk()
    results = await search_all(lk, "")
    assert results == []
    lk.list_rooms.assert_not_called()
    lk.get_all_participants_across_rooms.assert_not_called()


async def test_search_rooms_by_name():
    room = MagicMock()
    room.name = "my-room"
    room.metadata = ""
    room.num_participants = 2
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "my-room")
    assert any(r.kind == "room" and r.title == "my-room" for r in results)


async def test_search_rooms_by_metadata():
    room = MagicMock()
    room.name = "conference"
    room.metadata = "project-alpha"
    room.num_participants = 0
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "alpha")
    assert any(r.kind == "room" for r in results)


async def test_search_rooms_no_match():
    room = MagicMock()
    room.name = "unrelated"
    room.metadata = ""
    room.num_participants = 0
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "xyz-never-match")
    assert not any(r.kind == "room" for r in results)


async def test_search_case_insensitive():
    room = MagicMock()
    room.name = "MainRoom"
    room.metadata = ""
    room.num_participants = 1
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "mainroom")
    assert any(r.kind == "room" for r in results)


async def test_search_participants_by_identity():
    p = MagicMock()
    p.identity = "user-alice"
    p.name = ""
    p.metadata = ""
    p._room_name = "room-1"
    lk = _make_lk(
        get_all_participants_across_rooms=AsyncMock(return_value=[p])
    )
    results = await search_all(lk, "alice")
    assert any(r.kind == "participant" and "user-alice" in r.title for r in results)


async def test_search_participants_by_room_name():
    p = MagicMock()
    p.identity = "bob"
    p.name = ""
    p.metadata = ""
    p._room_name = "special-room"
    lk = _make_lk(
        get_all_participants_across_rooms=AsyncMock(return_value=[p])
    )
    results = await search_all(lk, "special")
    assert any(r.kind == "participant" for r in results)


async def test_search_egress_by_room_name():
    job = MagicMock()
    job.egress_id = "eg-001"
    job.room_name = "broadcast-room"
    job.status = 1
    lk = _make_lk(list_egress=AsyncMock(return_value=[job]))
    results = await search_all(lk, "broadcast")
    assert any(r.kind == "egress" for r in results)


async def test_search_ingress_by_name():
    stream = MagicMock()
    stream.ingress_id = "in-001"
    stream.name = "camera-feed"
    stream.room_name = "live-room"
    stream.url = "rtmp://host/live"
    stream.status = MagicMock()
    lk = _make_lk(list_ingress=AsyncMock(return_value=[stream]))
    results = await search_all(lk, "camera")
    assert any(r.kind == "ingress" for r in results)


async def test_search_result_url_for_room():
    room = MagicMock()
    room.name = "target"
    room.metadata = ""
    room.num_participants = 0
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "target")
    room_results = [r for r in results if r.kind == "room"]
    assert room_results[0].url == "/rooms/target"


async def test_search_api_error_returns_partial_results():
    """Errors on one entity type don't cancel others."""
    room = MagicMock()
    room.name = "healthy-room"
    room.metadata = ""
    room.num_participants = 1
    lk = _make_lk(
        list_rooms=AsyncMock(return_value=([room], 0.01)),
        get_all_participants_across_rooms=AsyncMock(side_effect=Exception("timeout")),
        list_egress=AsyncMock(side_effect=Exception("service down")),
    )
    results = await search_all(lk, "healthy")
    assert any(r.kind == "room" for r in results)
    assert not any(r.kind == "participant" for r in results)


async def test_search_result_is_dataclass():
    r = SearchResult(kind="room", title="t", subtitle="s", url="/rooms/t", status="active")
    assert r.kind == "room"
    assert r.title == "t"
    assert r.url == "/rooms/t"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/thinhda/Documents/codes/livekit-dashboard
python -m pytest tests/test_search.py -v 2>&1 | head -40
```

Expected: `ImportError` or `ModuleNotFoundError` for `app.services.search`.

- [ ] **Step 3: Implement app/services/search.py**

Create `app/services/search.py`:

```python
"""Global cross-entity search.

Fetches rooms, participants, egress jobs, and ingress streams concurrently
and returns a flat list of SearchResult items matching the query string.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """A single search hit with enough context to render a result row."""

    kind: str   # "room" | "participant" | "egress" | "ingress"
    title: str
    subtitle: str
    url: str
    status: str = ""


def _matches(q: str, *fields: str) -> bool:
    """Return True if q appears (case-insensitive) in any of the given fields."""
    ql = q.lower()
    return any(ql in (f or "").lower() for f in fields)


async def _search_rooms(lk, q: str) -> list[SearchResult]:
    try:
        rooms, _ = await lk.list_rooms()
    except Exception:
        return []
    out: list[SearchResult] = []
    for room in rooms:
        name = getattr(room, "name", "") or ""
        meta = getattr(room, "metadata", "") or ""
        if not _matches(q, name, meta):
            continue
        n = getattr(room, "num_participants", 0) or 0
        status = "active" if n > 0 else "idle"
        out.append(
            SearchResult(
                kind="room",
                title=name,
                subtitle=f"{n} participant{'s' if n != 1 else ''}",
                url=f"/rooms/{name}",
                status=status,
            )
        )
    return out


async def _search_participants(lk, q: str) -> list[SearchResult]:
    try:
        participants = await lk.get_all_participants_across_rooms()
    except Exception:
        return []
    out: list[SearchResult] = []
    for p in participants:
        identity = getattr(p, "identity", "") or ""
        name = getattr(p, "name", "") or ""
        meta = getattr(p, "metadata", "") or ""
        room_name = getattr(p, "_room_name", "") or ""
        if not _matches(q, identity, name, meta, room_name):
            continue
        display = name if name else identity
        out.append(
            SearchResult(
                kind="participant",
                title=display,
                subtitle=f"in {room_name}" if room_name else identity,
                url=f"/rooms/{room_name}" if room_name else "/rooms",
                status="connected",
            )
        )
    return out


async def _search_egress(lk, q: str) -> list[SearchResult]:
    try:
        jobs = await lk.list_egress(active=False)
    except Exception:
        return []
    out: list[SearchResult] = []
    for job in jobs:
        egress_id = getattr(job, "egress_id", "") or ""
        room_name = getattr(job, "room_name", "") or ""
        if not _matches(q, egress_id, room_name):
            continue
        out.append(
            SearchResult(
                kind="egress",
                title=egress_id,
                subtitle=f"room: {room_name}" if room_name else "recording job",
                url="/egress",
                status="active",
            )
        )
    return out


async def _search_ingress(lk, q: str) -> list[SearchResult]:
    try:
        streams = await lk.list_ingress()
    except Exception:
        return []
    out: list[SearchResult] = []
    for stream in streams:
        ingress_id = getattr(stream, "ingress_id", "") or ""
        name = getattr(stream, "name", "") or ""
        room_name = getattr(stream, "room_name", "") or ""
        url = getattr(stream, "url", "") or ""
        if not _matches(q, ingress_id, name, room_name, url):
            continue
        display = name if name else ingress_id
        out.append(
            SearchResult(
                kind="ingress",
                title=display,
                subtitle=f"room: {room_name}" if room_name else "ingress stream",
                url="/ingress",
                status="active",
            )
        )
    return out


async def search_all(lk, q: str) -> list[SearchResult]:
    """Search rooms, participants, egress, and ingress for *q*.

    Returns an empty list immediately when *q* is blank.
    Partial API failures return empty results for that entity type only.
    """
    if not q or not q.strip():
        return []

    batches = await asyncio.gather(
        _search_rooms(lk, q),
        _search_participants(lk, q),
        _search_egress(lk, q),
        _search_ingress(lk, q),
    )
    return [item for batch in batches for item in batch]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/thinhda/Documents/codes/livekit-dashboard
python -m pytest tests/test_search.py -v -k "not route"
```

Expected: all service tests PASS.

---

## Task 2: Search Route + Template

**Files:**
- Create: `app/routes/search.py`
- Create: `app/templates/search/results.html.j2`
- Modify: `app/main.py:129`
- Test: `tests/test_search.py` (route section, append to existing file)

**Interfaces:**
- Consumes: `search_all(lk, q) -> list[SearchResult]` from Task 1
- Produces: `GET /search` → HTML page with grouped results

- [ ] **Step 1: Write failing route integration test (append to tests/test_search.py)**

Add to the bottom of `tests/test_search.py`:

```python
# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------

def test_search_route_empty_q_returns_200(client, auth_headers):
    resp = client.get("/search?q=", headers=auth_headers)
    assert resp.status_code == 200


def test_search_route_requires_auth(client):
    resp = client.get("/search?q=hello", follow_redirects=False)
    assert resp.status_code == 401


def test_search_route_with_q_returns_200(client, auth_headers, monkeypatch):
    from app.services import search as search_mod

    async def _fake_search(lk, q):
        from app.services.search import SearchResult
        return [SearchResult(kind="room", title="test-room", subtitle="0 participants", url="/rooms/test-room", status="idle")]

    monkeypatch.setattr(search_mod, "search_all", _fake_search)
    resp = client.get("/search?q=test", headers=auth_headers)
    assert resp.status_code == 200
    assert b"test-room" in resp.content
```

- [ ] **Step 2: Run to confirm route tests fail**

```bash
cd /home/thinhda/Documents/codes/livekit-dashboard
python -m pytest tests/test_search.py::test_search_route_empty_q_returns_200 -v 2>&1 | head -20
```

Expected: `404 Not Found` (route not registered yet).

- [ ] **Step 3: Create app/routes/search.py**

```python
"""Global search route."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from typing import Optional

from app.services.livekit import LiveKitClient, get_livekit_client
from app.services.search import search_all
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token


router = APIRouter()


@router.get("/search", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def search_view(
    request: Request,
    q: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Global cross-entity search."""
    query = (q or "").strip()
    results = await search_all(lk, query) if query else []

    counts = {"room": 0, "participant": 0, "egress": 0, "ingress": 0}
    for r in results:
        counts[r.kind] = counts.get(r.kind, 0) + 1

    return request.app.state.templates.TemplateResponse(
        request,
        "search/results.html.j2",
        {
            "request": request,
            "q": query,
            "results": results,
            "counts": counts,
            "total": len(results),
            "current_user": get_current_user(request),
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
        },
    )
```

- [ ] **Step 4: Create app/templates/search/ directory and results.html.j2**

Create `app/templates/search/results.html.j2`:

```html
{% extends "base.html.j2" %}

{% block title %}Search — LiveKit Dashboard{% endblock %}

{% block page_title %}Search{% endblock %}
{% block page_subtitle %}
<p class="text-muted mb-0">
    {% if q %}
        {% if total > 0 %}{{ total }} result{{ 's' if total != 1 else '' }} for "<strong>{{ q }}</strong>"{% else %}No results for "<strong>{{ q }}</strong>"{% endif %}
    {% else %}
        Enter a search term above
    {% endif %}
</p>
{% endblock %}

{% block content %}
<div class="container-fluid px-4 py-4">

  <!-- Search form (inline repeat so user can refine without scrolling) -->
  <form action="/search" method="get" class="mb-4">
    <div class="input-group" style="max-width: 480px;">
      <span class="input-group-text"><i class="bi bi-search"></i></span>
      <input
        type="search"
        name="q"
        class="form-control"
        placeholder="Search rooms, participants, egress, ingress…"
        value="{{ q }}"
        autofocus
      >
      <button type="submit" class="btn btn-primary">Search</button>
    </div>
  </form>

  {% if not q %}
    {% include "partials/_empty_state.html.j2" with context %}
  {% elif total == 0 %}
    <div class="card border-0 bg-body-tertiary text-center py-5">
      <div class="card-body">
        <i class="bi bi-search fs-1 text-muted"></i>
        <p class="mt-3 text-muted">No matches found for "<strong>{{ q }}</strong>"</p>
        <small class="text-muted">Try a partial name, identity, or room name.</small>
      </div>
    </div>
  {% else %}
    {% set kinds = [
        ("room",        "bi-door-open",      "Rooms"),
        ("participant", "bi-person",         "Participants"),
        ("egress",      "bi-record-circle",  "Egress"),
        ("ingress",     "bi-cast",           "Ingress"),
    ] %}
    {% for kind, icon, label in kinds %}
      {% set group = results | selectattr("kind", "equalto", kind) | list %}
      {% if group %}
      <div class="mb-4">
        <h6 class="text-uppercase text-muted small fw-semibold mb-2">
          <i class="bi {{ icon }} me-1"></i>{{ label }}
          <span class="badge bg-secondary ms-1">{{ group | length }}</span>
        </h6>
        <div class="list-group">
          {% for item in group %}
          <a href="{{ item.url }}" class="list-group-item list-group-item-action d-flex align-items-center gap-3">
            <div class="flex-grow-1">
              <div class="fw-semibold">{{ item.title }}</div>
              <small class="text-muted">{{ item.subtitle }}</small>
            </div>
            {% if item.status %}
            <span class="badge bg-{{ item.status | status_color }}">{{ item.status }}</span>
            {% endif %}
          </a>
          {% endfor %}
        </div>
      </div>
      {% endif %}
    {% endfor %}
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 5: Register the search router in app/main.py**

In `app/main.py`, add the import and include. After the existing imports line:
```python
from app.routes import overview, rooms, egress, ingress, sip, settings, sandbox, auth, agents, homer
```
Change to:
```python
from app.routes import overview, rooms, egress, ingress, sip, settings, sandbox, auth, agents, homer, search
```

After `app.include_router(homer.router, tags=["Homer"])`, add:
```python
app.include_router(search.router, tags=["Search"])
```

- [ ] **Step 6: Run route tests to confirm they pass**

```bash
cd /home/thinhda/Documents/codes/livekit-dashboard
python -m pytest tests/test_search.py -v
```

Expected: All tests PASS.

---

## Task 3: Navigation Search Bar

**Files:**
- Create: `app/templates/partials/_search_bar.html.j2`
- Modify: `app/templates/base.html.j2:107-117`

**Interfaces:**
- Consumes: nothing (standalone HTML form)
- Produces: visible search input in top bar, submits to `GET /search?q=`

- [ ] **Step 1: Create app/templates/partials/_search_bar.html.j2**

```html
{# Compact search bar for top navigation.
   Usage: {% include "partials/_search_bar.html.j2" %} #}
<form action="/search" method="get" class="d-flex align-items-center" role="search">
  <div class="input-group input-group-sm" style="width: 220px;">
    <span class="input-group-text bg-transparent border-secondary">
      <i class="bi bi-search text-muted"></i>
    </span>
    <input
      type="search"
      name="q"
      class="form-control border-secondary bg-transparent text-light"
      placeholder="Search…"
      value="{{ q if q is defined else '' }}"
      aria-label="Global search"
    >
  </div>
</form>
```

- [ ] **Step 2: Embed search bar in base.html.j2 top-bar actions**

In `app/templates/base.html.j2`, locate the `top-bar-actions` div (around line 107):

```html
            <div class="top-bar-actions">
                <div class="user-menu">
```

Change it to:

```html
            <div class="top-bar-actions">
                {% include "partials/_search_bar.html.j2" %}
                <div class="user-menu">
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
cd /home/thinhda/Documents/codes/livekit-dashboard
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all previously passing tests still pass; new `test_search.py` tests all pass.

---

## Self-Review

### Spec Coverage
- [x] Global search endpoint `GET /search?q=` — Task 2
- [x] Searches rooms, participants, egress, ingress — Task 1
- [x] Reuses shared `filters.py`/`formatters.py` — `status_color` filter used in template; `parse_filters` not used since search has a single dedicated `?q=` param (keeping it minimal per YAGNI)
- [x] Reuses existing partials (`_empty_state`, `_status_badge`) — `_empty_state` included in results template
- [x] Tests added/updated — Task 1 (service tests) + Task 2 (route tests)
- [x] Navigation search bar — Task 3

### Placeholder Scan
- No TBD/TODO markers
- All code blocks are complete implementations
- All test assertions check specific behavior

### Type Consistency
- `SearchResult` defined in Task 1, consumed in Task 1 tests and Task 2 monkeypatch — same import path `app.services.search`
- `search_all(lk, q)` signature consistent across service, route, and monkeypatch
- `counts` dict keys (`"room"`, `"participant"`, `"egress"`, `"ingress"`) match `SearchResult.kind` values and template iteration

### Notes on Remaining Work
- The `_empty_state.html.j2` include in `results.html.j2` passes no parameters, so it will render with default/empty values — this is acceptable for the "no query entered" state; the template can be refined post-slice.
- `list_egress(active=False)` searches all jobs (not just active) so historical egress can also be found. If this proves too slow on large servers, restrict to `active=True`.
