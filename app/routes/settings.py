"""Settings and configuration routes"""

import os
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.livekit import LiveKitClient, get_livekit_client
from app.services import security_log
from app.services import ip_allowlist as ip_allowlist_service
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


def _mask_secret(value: str, visible: int = 4) -> str:
    """Mask a secret, showing only the first/last `visible` characters."""
    if not value:
        return "(not set)"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * (len(value) - visible * 2)}{value[-visible:]}"


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def settings_index(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Display settings and configuration"""
    current_user = get_current_user(request)

    # Get server info
    server_info = await lk.get_server_info()

    # Mask sensitive information before it ever reaches the template
    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")

    config = {
        "livekit_url": lk.url,
        "status": server_info.get("status", "unknown"),
        "debug": os.environ.get("DEBUG", "false").lower() == "true",
        "sip_enabled": os.environ.get("ENABLE_SIP", "false").lower() == "true",
        "api_key_masked": _mask_secret(api_key),
        "api_secret_masked": _mask_secret(api_secret),
    }

    return request.app.state.templates.TemplateResponse(request,
        "settings.html.j2",
        {
            "request": request,
            "config": config,
            "current_user": current_user,
            "csrf_token": get_csrf_token(request),
            "failed_logins": security_log.list_failed_logins(limit=20),
            "failed_login_counts": security_log.count_by_ip(),
            "ip_allowlist_raw": ", ".join(ip_allowlist_service.get_allowlist()),
        },
    )


@router.post("/settings/security", dependencies=[Depends(requires_admin)])
async def save_security_settings(
    request: Request,
    csrf_token: str = Form(...),
    ip_allowlist: str = Form(""),
):
    """Update the IP allowlist from the Settings page."""
    await verify_csrf_token(request)
    requester_ip = request.client.host if request.client else "unknown"
    ip_allowlist_service.save_allowlist(ip_allowlist, requester_ip=requester_ip)
    return RedirectResponse(url="/settings", status_code=303)
