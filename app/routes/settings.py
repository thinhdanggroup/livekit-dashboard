"""Settings and configuration routes"""

import os
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token


router = APIRouter()


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def settings_index(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Display settings and configuration"""
    current_user = get_current_user(request)

    # Get server info
    server_info = await lk.get_server_info()

    # Mask sensitive information
    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")

    config = {
        "livekit_url": lk.url,
        "status": server_info.get("status", "unknown"),
        "sip_enabled": lk.sip_enabled,
        "debug": os.environ.get("DEBUG", "false").lower() == "true",
    }

    return request.app.state.templates.TemplateResponse(
        "settings.html.j2",
        {
            "request": request,
            "config": config,
            "current_user": current_user,
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
        },
    )
