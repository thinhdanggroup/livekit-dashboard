"""Room management routes"""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from typing import Optional

from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/rooms", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def rooms_index(
    request: Request,
    search: Optional[str] = None,
    partial: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """List all rooms with optional search"""
    rooms, latency = await lk.list_rooms()
    latency_ms = round(latency * 1000, 2)

    # Filter by search if provided
    if search:
        rooms = [r for r in rooms if search.lower() in r.name.lower()]

    current_user = get_current_user(request)

    template_data = {
        "request": request,
        "rooms": rooms,
        "latency_ms": latency_ms,
        "search": search,
        "current_user": current_user,
        "sip_enabled": lk.sip_enabled,
        "csrf_token": get_csrf_token(request),
    }

    # Return partial template for HTMX polling
    if partial:
        return request.app.state.templates.TemplateResponse(
            "rooms/index.html.j2",
            template_data,
        )

    return request.app.state.templates.TemplateResponse(
        "rooms/index.html.j2",
        template_data,
    )


@router.post("/rooms", dependencies=[Depends(requires_admin)])
async def create_room(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    max_participants: int = Form(100),
    empty_timeout: int = Form(300),
    metadata: str = Form(""),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Create a new room"""
    await verify_csrf_token(request)

    try:
        await lk.create_room(
            name=name,
            max_participants=max_participants,
            empty_timeout=empty_timeout,
            metadata=metadata,
        )
        
        # Check if HTMX request
        if request.headers.get("HX-Request"):
            # Return just the rooms list for HTMX
            rooms, latency = await lk.list_rooms()
            latency_ms = round(latency * 1000, 2)
            current_user = get_current_user(request)
            
            return request.app.state.templates.TemplateResponse(
                "rooms/_rooms_table.html.j2",
                {
                    "request": request,
                    "rooms": rooms,
                    "latency_ms": latency_ms,
                    "current_user": current_user,
                    "sip_enabled": lk.sip_enabled,
                    "csrf_token": get_csrf_token(request),
                },
            )
        
        return RedirectResponse(url="/rooms", status_code=303)
    except Exception as e:
        # In a real app, you'd want to show this error to the user
        print(f"Error creating room: {e}")
        return RedirectResponse(url="/rooms", status_code=303)


@router.get(
    "/rooms/{room_name}", response_class=HTMLResponse, dependencies=[Depends(requires_admin)]
)
async def room_detail(
    request: Request,
    room_name: str,
    partial: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Display room details and participants"""
    rooms, _ = await lk.list_rooms(names=[room_name])
    room = rooms[0] if rooms else None
    if not room:
        return RedirectResponse(url="/rooms", status_code=303)

    participants = await lk.list_participants(room_name)
    current_user = get_current_user(request)

    template_data = {
        "request": request,
        "room": room,
        "participants": participants,
        "current_user": current_user,
        "sip_enabled": lk.sip_enabled,
        "csrf_token": get_csrf_token(request),
    }

    # Return partial for HTMX polling
    if partial:
        return request.app.state.templates.TemplateResponse(
            "rooms/detail.html.j2",
            template_data,
        )

    return request.app.state.templates.TemplateResponse(
        "rooms/detail.html.j2",
        template_data,
    )


@router.post("/rooms/{room_name}/delete", dependencies=[Depends(requires_admin)])
async def delete_room(
    request: Request,
    room_name: str,
    csrf_token: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Delete/close a room"""
    await verify_csrf_token(request)
    
    try:
        await lk.delete_room(room_name)
    except Exception as e:
        print(f"Error deleting room: {e}")

    # Check if HTMX request
    if request.headers.get("HX-Request"):
        # Return updated rooms list
        rooms, latency = await lk.list_rooms()
        latency_ms = round(latency * 1000, 2)
        current_user = get_current_user(request)
        
        # Return just the rooms table HTML
        return request.app.state.templates.TemplateResponse(
            "rooms/_rooms_table.html.j2",
            {
                "request": request,
                "rooms": rooms,
                "latency_ms": latency_ms,
                "current_user": current_user,
                "sip_enabled": lk.sip_enabled,
                "csrf_token": get_csrf_token(request),
            },
        )

    return RedirectResponse(url="/rooms", status_code=303)


@router.post("/rooms/{room_name}/token", dependencies=[Depends(requires_admin)])
async def generate_room_token(
    request: Request,
    room_name: str,
    csrf_token: str = Form(...),
    identity: str = Form(...),
    participant_name: Optional[str] = Form(None),
    ttl: int = Form(3600),
    can_publish: Optional[str] = Form(None),
    can_subscribe: Optional[str] = Form(None),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Generate a join token for the room"""
    await verify_csrf_token(request)

    try:
        token = lk.generate_token(
            room=room_name,
            identity=identity,
            name=participant_name,
            ttl=ttl,
            can_publish=(can_publish == "on"),
            can_subscribe=(can_subscribe == "on"),
        )

        # Return token as plain text or JSON
        # For now, redirect back with token in query (not ideal for production)
        # In production, you'd show this in a modal or copy-to-clipboard
        return Response(
            content=f"Token: {token}",
            media_type="text/plain",
        )
    except Exception as e:
        print(f"Error generating token: {e}")
        return RedirectResponse(url=f"/rooms/{room_name}", status_code=303)


@router.post(
    "/rooms/{room_name}/participants/{identity}/kick",
    dependencies=[Depends(requires_admin)],
)
async def kick_participant(
    request: Request,
    room_name: str,
    identity: str,
    csrf_token: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Kick a participant from the room"""
    await verify_csrf_token(request)

    try:
        await lk.remove_participant(room_name, identity)
    except Exception as e:
        print(f"Error kicking participant: {e}")

    return RedirectResponse(url=f"/rooms/{room_name}", status_code=303)


@router.post(
    "/rooms/{room_name}/participants/{identity}/mute",
    dependencies=[Depends(requires_admin)],
)
async def mute_participant(
    request: Request,
    room_name: str,
    identity: str,
    csrf_token: str = Form(...),
    track_sid: str = Form(...),
    muted: bool = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Mute/unmute a participant's track"""
    await verify_csrf_token(request)

    try:
        await lk.mute_participant_track(room_name, identity, track_sid, muted)
    except Exception as e:
        print(f"Error muting participant: {e}")

    return RedirectResponse(url=f"/rooms/{room_name}", status_code=303)


@router.get(
    "/rooms/{room_name}/rtc-stats", 
    dependencies=[Depends(requires_admin)]
)
async def get_room_rtc_stats(
    request: Request,
    room_name: str,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Get RTC statistics for a room via direct connection"""
    try:
        stats_dict, latency = await lk.get_room_rtc_stats(room_name)
        
        return {
            "success": True,
            "data": stats_dict,
            "latency_ms": round(latency, 2)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "room_name": room_name
        }
