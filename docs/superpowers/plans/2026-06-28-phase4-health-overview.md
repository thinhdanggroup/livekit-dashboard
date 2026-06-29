# Phase 4: Health Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a concise health summary bar at the top of the overview page, wired to `gather_dashboard_stats`, and clean the overview route of debug prints and mock analytics helpers.

**Architecture:** `gather_dashboard_stats()` (already in `app/services/dashboard.py`) becomes the single source of top-line metrics. The route calls it once and passes the result as `health_stats` to the template. The existing expandable analytics sections are unchanged — they still consume the full analytics dicts. The health bar is rendered via a new `_health_summary.html.j2` partial using existing `.stats-grid` / `.stat-card` CSS.

**Tech Stack:** FastAPI, Jinja2, Bootstrap 5, existing dark-theme CSS variables.

## Global Constraints

- No new Python packages.
- Do not alter `gather_dashboard_stats` signature or `DashboardStats` fields.
- Keep existing expandable analytics sections intact.
- No commits or pushes.

---

### Task 1: Clean up `app/routes/overview.py`

**Files:**
- Modify: `app/routes/overview.py`

**Interfaces:**
- Consumes: `gather_dashboard_stats(lk: LiveKitClient) -> DashboardStats` from `app.services.dashboard`
- Produces: template context key `health_stats: DashboardStats`

- [ ] **Step 1: Remove `get_mock_analytics_data` and `get_real_analytics_data`**

Delete both functions entirely — `gather_dashboard_stats` subsumes them.

- [ ] **Step 2: Add import and rewrite the route**

```python
"""Overview/Dashboard routes"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.services.livekit import LiveKitClient, get_livekit_client
from app.services.dashboard import gather_dashboard_stats
from app.security.basic_auth import requires_admin, get_current_user


router = APIRouter()


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def overview(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Display overview dashboard with health summary and analytics"""
    health_stats = await gather_dashboard_stats(lk)

    server_info = await lk.get_server_info()
    room_analytics = await lk.get_room_analytics()
    egress_analytics = await lk.get_egress_analytics()
    ingress_analytics = await lk.get_ingress_analytics()

    sip_analytics = None
    if lk.sip_enabled:
        try:
            sip_analytics = await lk.get_sip_analytics()
        except Exception:
            pass

    # Derive analytics dict for existing chart sections from health_stats
    analytics = {
        "connection_success": health_stats.connection_success_pct,
        "connection_minutes": health_stats.connection_minutes,
        "platforms": health_stats.platforms,
        "connection_types": health_stats.connection_types,
    }

    current_user = get_current_user(request)

    return request.app.state.templates.TemplateResponse(
        request,
        "index.html.j2",
        {
            "request": request,
            "health_stats": health_stats,
            "server_info": server_info,
            "analytics": analytics,
            "room_analytics": room_analytics,
            "egress_analytics": egress_analytics,
            "ingress_analytics": ingress_analytics,
            "sip_analytics": sip_analytics,
            "last_updated": "6 min",
            "current_user": current_user,
            "sip_enabled": lk.sip_enabled,
        },
    )
```

- [ ] **Step 3: Run existing tests to confirm no regression**

```bash
python -m pytest tests/test_main.py tests/test_dashboard_service.py -v
```

Expected: All existing tests pass.

---

### Task 2: Add health summary partial template

**Files:**
- Create: `app/templates/partials/_health_summary.html.j2`

**Interfaces:**
- Consumes: `health_stats` (DashboardStats dataclass), `sip_enabled` (bool)
- Produces: rendered health bar HTML included by `index.html.j2`

- [ ] **Step 1: Create the partial**

```jinja2
{#
  Health summary bar — top-of-page live status strip.
  Parameters:
    health_stats  (DashboardStats)  — from gather_dashboard_stats()
    sip_enabled   (bool)            — whether SIP is configured
#}
{% if health_stats.error %}
<div class="alert alert-danger d-flex align-items-center gap-2 mb-3" role="alert">
    <i class="bi bi-exclamation-triangle-fill"></i>
    <span>LiveKit API error: {{ health_stats.error }}</span>
</div>
{% endif %}

<div class="stats-grid mb-4">
    <div class="stat-card">
        <div class="stat-label">Total Rooms</div>
        <div class="stat-value">{{ health_stats.rooms_total }}</div>
        <div class="stat-change">{{ health_stats.rooms_active }} active</div>
    </div>

    <div class="stat-card">
        <div class="stat-label">Participants</div>
        <div class="stat-value info">{{ health_stats.participants_total }}</div>
        <div class="stat-change">across all rooms</div>
    </div>

    <div class="stat-card">
        <div class="stat-label">Active Egress</div>
        <div class="stat-value {% if health_stats.egress_active > 0 %}success{% endif %}">
            {{ health_stats.egress_active }}
        </div>
        <div class="stat-change">recording / streaming jobs</div>
    </div>

    <div class="stat-card">
        <div class="stat-label">Active Ingress</div>
        <div class="stat-value {% if health_stats.ingress_active > 0 %}success{% endif %}">
            {{ health_stats.ingress_active }}
        </div>
        <div class="stat-change">live streams</div>
    </div>

    {% if sip_enabled %}
    <div class="stat-card">
        <div class="stat-label">SIP Trunks</div>
        <div class="stat-value {% if health_stats.sip_trunks > 0 %}success{% endif %}">
            {{ health_stats.sip_trunks }}
        </div>
        <div class="stat-change">telephony enabled</div>
    </div>
    {% endif %}

    <div class="stat-card">
        <div class="stat-label">API Latency</div>
        <div class="stat-value {% if health_stats.api_latency_ms > 200 %}danger{% elif health_stats.api_latency_ms > 100 %}info{% endif %}">
            {{ health_stats.api_latency_ms }}
        </div>
        <div class="stat-change">ms</div>
    </div>
</div>
```

---

### Task 3: Include health summary in `index.html.j2`

**Files:**
- Modify: `app/templates/index.html.j2`

**Interfaces:**
- Consumes: `_health_summary.html.j2` partial, `health_stats`, `sip_enabled`

- [ ] **Step 1: Add include at top of `{% block content %}`**

After the opening `{% block content %}` tag and before the `<!-- Get Started Section -->` comment, add:

```jinja2
<!-- Health Summary -->
{% include "partials/_health_summary.html.j2" %}
```

- [ ] **Step 2: Verify template renders without errors**

Run: `python -m pytest tests/test_main.py -v`

---

### Task 4: Update route test for health_stats context

**Files:**
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add mocked overview test**

```python
from unittest.mock import AsyncMock, MagicMock, patch


def test_overview_with_mocked_lk(client, auth_headers):
    """Overview route returns 200 and includes health summary when LiveKit is mocked."""
    from app.services.dashboard import DashboardStats

    mock_stats = DashboardStats(
        rooms_total=3,
        rooms_active=2,
        participants_total=7,
        egress_active=1,
        ingress_active=0,
        api_latency_ms=12.5,
    )
    mock_room_analytics = {
        "total_rooms": 3,
        "active_rooms": 2,
        "empty_rooms": 1,
        "total_participants": 7,
        "avg_participants": 2.3,
        "room_sizes": {"small": 2, "medium": 0, "large": 0},
        "api_latency_ms": 12.5,
    }
    mock_egress = {
        "active_jobs": 1,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "success_rate": 100,
        "egress_types": {"room_composite": 1, "participant": 0, "track": 0, "web": 0},
        "storage_used_gb": 0,
        "total_jobs_today": 1,
    }
    mock_ingress = {
        "total_ingress": 0,
        "active_ingress": 0,
        "ingress_types": {"rtmp": 0, "whip": 0, "url": 0},
        "avg_bitrate_mbps": 0,
        "connection_stability": 0,
        "streams_today": 0,
    }
    mock_server_info = {"rooms_count": 3, "participants_count": 7, "version": "1.0"}

    with patch("app.routes.overview.gather_dashboard_stats", new=AsyncMock(return_value=mock_stats)), \
         patch("app.services.livekit.LiveKitClient.get_server_info", new=AsyncMock(return_value=mock_server_info)), \
         patch("app.services.livekit.LiveKitClient.get_room_analytics", new=AsyncMock(return_value=mock_room_analytics)), \
         patch("app.services.livekit.LiveKitClient.get_egress_analytics", new=AsyncMock(return_value=mock_egress)), \
         patch("app.services.livekit.LiveKitClient.get_ingress_analytics", new=AsyncMock(return_value=mock_ingress)):
        response = client.get("/", headers=auth_headers)

    assert response.status_code == 200
    assert "Total Rooms" in response.text
    assert "Participants" in response.text
    assert "Active Egress" in response.text
```

- [ ] **Step 2: Run all relevant tests**

```bash
python -m pytest tests/test_main.py tests/test_dashboard_service.py tests/test_utils.py -v
```

Expected: All pass.
