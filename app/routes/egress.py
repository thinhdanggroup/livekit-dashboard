"""Egress/Recording routes"""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from datetime import datetime

from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/egress", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def egress_index(
    request: Request,
    partial: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """List all egress jobs"""
    egress_jobs = await lk.list_egress(active=True)
    current_user = get_current_user(request)

    template_data = {
        "request": request,
        "egress_jobs": egress_jobs,
        "current_user": current_user,
        "sip_enabled": lk.sip_enabled,
        "csrf_token": get_csrf_token(request),
    }

    # Return partial for HTMX polling
    if partial:
        return request.app.state.templates.TemplateResponse(
            "egress/index.html.j2",
            template_data,
        )

    return request.app.state.templates.TemplateResponse(
        "egress/index.html.j2",
        template_data,
    )


@router.post("/egress/start", dependencies=[Depends(requires_admin)])
async def start_egress(
    request: Request,
    csrf_token: str = Form(...),
    room_name: str = Form(...),
    output_filename: str = Form(...),
    layout: str = Form("grid"),
    audio_only: Optional[str] = Form(None),
    video_only: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Start a room composite egress"""
    await verify_csrf_token(request)

    try:
        # Replace placeholders in filename
        filename = output_filename.replace("{room}", room_name)
        filename = filename.replace("{time}", datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        await lk.start_room_composite_egress(
            room_name=room_name,
            output_filename=filename,
            layout=layout,
            audio_only=(audio_only == "on"),
            video_only=(video_only == "on"),
        )
    except Exception as e:
        print(f"Error starting egress: {e}")

    return RedirectResponse(url="/egress", status_code=303)


@router.post("/egress/{egress_id}/stop", dependencies=[Depends(requires_admin)])
async def stop_egress(
    request: Request,
    egress_id: str,
    csrf_token: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Stop an egress job"""
    await verify_csrf_token(request)
    
    try:
        await lk.stop_egress(egress_id)
    except Exception as e:
        print(f"Error stopping egress: {e}")

    return RedirectResponse(url="/egress", status_code=303)
