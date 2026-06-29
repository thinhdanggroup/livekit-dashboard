"""Ingress management routes"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional

from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/ingress", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def ingress_index(
    request: Request,
    flash_message: Optional[str] = None,
    flash_type: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """List all ingress streams"""
    try:
        ingress_list = await lk.list_ingress()
    except Exception:
        ingress_list = []
    current_user = get_current_user(request)

    return request.app.state.templates.TemplateResponse(request, 
        "ingress/index.html.j2",
        {
            "request": request,
            "ingress_list": ingress_list,
            "current_user": current_user,
            "csrf_token": get_csrf_token(request),
            "flash_message": flash_message,
            "flash_type": flash_type,
        },
    )


@router.post("/ingress/create", dependencies=[Depends(requires_admin)])
async def create_ingress(
    request: Request,
    csrf_token: str = Form(...),
    ingress_type: str = Form("rtmp"),
    name: str = Form(...),
    room_name: str = Form(...),
    participant_identity: Optional[str] = Form(None),
    participant_name: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Create a new ingress stream"""
    await verify_csrf_token(request)
    try:
        result = await lk.create_ingress(
            ingress_type=ingress_type,
            name=name,
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
            metadata=metadata,
        )
        ingress_id = getattr(result, "ingress_id", "")
        msg = quote(f"Ingress '{name}' created (ID: {ingress_id})")
        return RedirectResponse(url=f"/ingress?flash_message={msg}&flash_type=success", status_code=303)
    except Exception as e:
        msg = quote(f"Error creating ingress: {e}")
        return RedirectResponse(url=f"/ingress?flash_message={msg}&flash_type=danger", status_code=303)


@router.post("/ingress/update", dependencies=[Depends(requires_admin)])
async def update_ingress(
    request: Request,
    csrf_token: str = Form(...),
    ingress_id: str = Form(...),
    name: Optional[str] = Form(None),
    room_name: Optional[str] = Form(None),
    participant_identity: Optional[str] = Form(None),
    participant_name: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Update an ingress stream"""
    await verify_csrf_token(request)
    try:
        await lk.update_ingress(
            ingress_id=ingress_id,
            name=name,
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
            metadata=metadata,
        )
        msg = quote(f"Ingress updated")
        return RedirectResponse(url=f"/ingress?flash_message={msg}&flash_type=success", status_code=303)
    except Exception as e:
        msg = quote(f"Error updating ingress: {e}")
        return RedirectResponse(url=f"/ingress?flash_message={msg}&flash_type=danger", status_code=303)


@router.post("/ingress/delete", dependencies=[Depends(requires_admin)])
async def delete_ingress(
    request: Request,
    csrf_token: str = Form(...),
    ingress_id: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Delete an ingress stream"""
    await verify_csrf_token(request)
    try:
        await lk.delete_ingress(ingress_id=ingress_id)
        msg = quote("Ingress deleted")
        return RedirectResponse(url=f"/ingress?flash_message={msg}&flash_type=success", status_code=303)
    except Exception as e:
        msg = quote(f"Error deleting ingress: {e}")
        return RedirectResponse(url=f"/ingress?flash_message={msg}&flash_type=danger", status_code=303)
