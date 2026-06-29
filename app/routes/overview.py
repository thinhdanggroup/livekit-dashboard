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
