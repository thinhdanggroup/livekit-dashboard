"""Overview/Dashboard routes"""

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from app.services.livekit import LiveKitClient, get_livekit_client
from app.services.dashboard import gather_dashboard_stats
from app.services import anomaly
from app.security.basic_auth import requires_admin, get_current_user
from app.utils.filters import parse_filters


router = APIRouter()


@router.get("/export.json", dependencies=[Depends(requires_admin)])
async def export_overview_json(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Export the current overview snapshot as JSON."""
    filters = parse_filters(request)
    (
        health_stats,
        server_info,
        room_analytics,
        egress_analytics,
        ingress_analytics,
    ) = await asyncio.gather(
        gather_dashboard_stats(lk),
        lk.get_server_info(),
        lk.get_room_analytics(),
        lk.get_egress_analytics(),
        lk.get_ingress_analytics(),
    )

    payload = {
        "filters": filters.as_query_params(),
        "health_stats": jsonable_encoder(health_stats),
        "server_info": server_info,
        "room_analytics": room_analytics,
        "egress_analytics": egress_analytics,
        "ingress_analytics": ingress_analytics,
    }
    return JSONResponse(payload)


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def overview(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    filters = parse_filters(request)
    """Display overview dashboard with health summary and analytics"""

    gather_tasks = [
        gather_dashboard_stats(lk),
        lk.get_server_info(),
        lk.get_room_analytics(),
        lk.get_egress_analytics(),
        lk.get_ingress_analytics(),
    ]
    if lk.sip_enabled:
        gather_tasks.append(lk.get_sip_analytics())

    results = await asyncio.gather(*gather_tasks, return_exceptions=True)

    health_stats   = results[0] if not isinstance(results[0], Exception) else None
    server_info    = results[1] if not isinstance(results[1], Exception) else {}
    room_analytics = results[2] if not isinstance(results[2], Exception) else {}
    egress_analytics  = results[3] if not isinstance(results[3], Exception) else {}
    ingress_analytics = results[4] if not isinstance(results[4], Exception) else {}
    sip_analytics  = (results[5] if not isinstance(results[5], Exception) else None) if lk.sip_enabled else None

    if health_stats is None:
        from app.services.dashboard import DashboardStats
        health_stats = DashboardStats()

    # Derive analytics dict for existing chart sections from health_stats
    analytics = {
        "connection_success": health_stats.connection_success_pct,
        "connection_minutes": health_stats.connection_minutes,
        "platforms": health_stats.platforms,
        "connection_types": health_stats.connection_types,
    }

    current_user = get_current_user(request)
    observations = anomaly.detect(health_stats)

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
            "filters": filters,
            "observations": observations,
        },
    )
