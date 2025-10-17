"""Token generator sandbox routes"""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from typing import Optional
from urllib.parse import urlencode

from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/sandbox", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def sandbox_index(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Display token generator sandbox"""
    current_user = get_current_user(request)

    return request.app.state.templates.TemplateResponse(
        "sandbox.html.j2",
        {
            "request": request,
            "current_user": current_user,
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
            "form_data": {},
            "token": None,
            "test_url": None,
        },
    )


@router.post(
    "/sandbox/generate", response_class=HTMLResponse, dependencies=[Depends(requires_admin)]
)
async def generate_sandbox_token(
    request: Request,
    csrf_token: str = Form(...),
    room: str = Form(...),
    identity: str = Form(...),
    name: Optional[str] = Form(None),
    ttl: int = Form(3600),
    metadata: str = Form(""),
    can_publish: Optional[str] = Form(None),
    can_subscribe: Optional[str] = Form(None),
    can_publish_data: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Generate a test token"""
    await verify_csrf_token(request)

    current_user = get_current_user(request)

    # Generate token
    token = lk.generate_token(
        room=room,
        identity=identity,
        name=name,
        ttl=ttl,
        metadata=metadata,
        can_publish=(can_publish == "on"),
        can_subscribe=(can_subscribe == "on"),
        can_publish_data=(can_publish_data == "on"),
    )

    # Generate test URL for LiveKit Meet (example)
    # Note: Update this URL based on your actual LiveKit Meet deployment
    test_params = {
        "url": lk.url,
        "token": token,
    }
    test_url = f"https://meet.livekit.io/custom?{urlencode(test_params)}"

    # Store form data to pre-fill
    form_data = {
        "room": room,
        "identity": identity,
        "name": name,
        "ttl": ttl,
        "metadata": metadata,
        "can_publish": (can_publish == "on"),
        "can_subscribe": (can_subscribe == "on"),
        "can_publish_data": (can_publish_data == "on"),
    }

    return request.app.state.templates.TemplateResponse(
        "sandbox.html.j2",
        {
            "request": request,
            "current_user": current_user,
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
            "form_data": form_data,
            "token": token,
            "test_url": test_url,
        },
    )
