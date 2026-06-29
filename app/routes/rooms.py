"""Room management routes"""

import csv
import io
import logging
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from typing import List, Optional

from app.services.livekit import LiveKitClient, get_livekit_client
from app.services import room_annotations as annotations
from app.services import audit_log
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token
from app.utils.filters import parse_filters

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/rooms", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def rooms_index(
    request: Request,
    search: Optional[str] = None,
    partial: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """List all rooms with optional search"""
    filters = parse_filters(request)
    search = (search or filters.q).strip()

    try:
        rooms, latency = await lk.list_rooms()
    except Exception:
        rooms, latency = [], 0.0
    latency_ms = round(latency * 1000, 2)

    # Filter by search if provided
    if search:
        rooms = [r for r in rooms if search.lower() in r.name.lower()]

    current_user = get_current_user(request)
    pinned_names = annotations.get_pinned()
    all_annotations = annotations.get_all_annotations()

    def _annotate(room):
        room._pinned = room.name in pinned_names
        room._tags = all_annotations.get("tags", {}).get(room.name, [])
        room._note = all_annotations.get("notes", {}).get(room.name, "")
        return room

    rooms = [_annotate(r) for r in rooms]
    pinned_rooms = [r for r in rooms if r._pinned]
    unpinned_rooms = [r for r in rooms if not r._pinned]

    template_data = {
        "request": request,
        "rooms": unpinned_rooms,
        "pinned_rooms": pinned_rooms,
        "latency_ms": latency_ms,
        "search": search,
        "filters": filters,
        "current_user": current_user,
        "csrf_token": get_csrf_token(request),
    }

    # Return partial table for HTMX polling
    if partial:
        return request.app.state.templates.TemplateResponse(request,
            "rooms/_rooms_table.html.j2",
            template_data,
        )

    return request.app.state.templates.TemplateResponse(request,
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
        audit_log.log_action("room.create", name, user=get_current_user(request) or "admin",
                             details={"max_participants": max_participants})

        # Check if HTMX request
        if request.headers.get("HX-Request"):
            # Return just the rooms list for HTMX
            rooms, latency = await lk.list_rooms()
            latency_ms = round(latency * 1000, 2)
            current_user = get_current_user(request)
            
            return request.app.state.templates.TemplateResponse(request, 
                "rooms/_rooms_table.html.j2",
                {
                    "request": request,
                    "rooms": rooms,
                    "latency_ms": latency_ms,
                    "current_user": current_user,
                    "csrf_token": get_csrf_token(request),
                },
            )
        
        return RedirectResponse(url="/rooms", status_code=303)
    except Exception as e:
        # In a real app, you'd want to show this error to the user
        logger.warning("Error creating room: %s", e)
        return RedirectResponse(url="/rooms", status_code=303)


@router.get("/rooms/export.csv", dependencies=[Depends(requires_admin)])
async def export_rooms_csv(
    request: Request,
    search: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Export current rooms list as CSV, respecting search filter"""
    filters = parse_filters(request)
    search = (search or filters.q).strip()

    try:
        rooms, _ = await lk.list_rooms()
    except Exception:
        rooms = []

    if search:
        rooms = [r for r in rooms if search.lower() in r.name.lower()]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "num_participants", "max_participants", "creation_time", "empty_timeout", "metadata"])
    for room in rooms:
        writer.writerow([
            room.name,
            room.num_participants,
            room.max_participants,
            room.creation_time,
            room.empty_timeout,
            room.metadata or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rooms.csv"},
    )


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
    room_annotations = annotations.get_annotations(room_name)
    timeline = annotations.build_timeline(room, participants)

    template_data = {
        "request": request,
        "room": room,
        "participants": participants,
        "current_user": current_user,
        "csrf_token": get_csrf_token(request),
        "annotations": room_annotations,
        "timeline": timeline,
        "preset_tags": annotations.PRESET_TAGS,
    }

    # Return partial for HTMX polling
    if partial:
        return request.app.state.templates.TemplateResponse(request,
            "rooms/detail.html.j2",
            template_data,
        )

    return request.app.state.templates.TemplateResponse(request,
        "rooms/detail.html.j2",
        template_data,
    )


@router.post("/rooms/{room_name}/update", dependencies=[Depends(requires_admin)])
async def update_room(
    request: Request,
    room_name: str,
    csrf_token: str = Form(...),
    metadata: str = Form(""),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Update a room's metadata"""
    await verify_csrf_token(request)
    try:
        await lk.update_room_metadata(room_name, metadata)
    except Exception as e:
        logger.warning("Error updating room: %s", e)
    return RedirectResponse(url=f"/rooms/{room_name}", status_code=303)


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
        audit_log.log_action("room.delete", room_name, user=get_current_user(request) or "admin")
    except Exception as e:
        logger.warning("Error deleting room: %s", e)

    # Check if HTMX request
    if request.headers.get("HX-Request"):
        # Return updated rooms list
        rooms, latency = await lk.list_rooms()
        latency_ms = round(latency * 1000, 2)
        current_user = get_current_user(request)
        
        # Return just the rooms table HTML
        return request.app.state.templates.TemplateResponse(request, 
            "rooms/_rooms_table.html.j2",
            {
                "request": request,
                "rooms": rooms,
                "latency_ms": latency_ms,
                "current_user": current_user,
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
        logger.warning("Error generating token: %s", e)
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
        audit_log.log_action("participant.kick", identity, user=get_current_user(request) or "admin",
                             details={"room": room_name})
    except Exception as e:
        logger.warning("Error kicking participant: %s", e)

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
        action = "participant.mute" if muted else "participant.unmute"
        audit_log.log_action(action, identity, user=get_current_user(request) or "admin",
                             details={"room": room_name, "track_sid": track_sid})
    except Exception as e:
        logger.warning("Error muting participant: %s", e)

    return RedirectResponse(url=f"/rooms/{room_name}", status_code=303)


@router.post(
    "/rooms/{room_name}/participants/{identity}/update",
    dependencies=[Depends(requires_admin)],
)
async def update_participant(
    request: Request,
    room_name: str,
    identity: str,
    csrf_token: str = Form(...),
    metadata: str = Form(""),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Update a participant's metadata"""
    await verify_csrf_token(request)
    try:
        await lk.update_participant(room_name, identity, metadata=metadata)
    except Exception as e:
        logger.warning("Error updating participant: %s", e)
    return RedirectResponse(url=f"/rooms/{room_name}", status_code=303)


@router.post("/rooms/{room_name}/pin", dependencies=[Depends(requires_admin)])
async def pin_room(
    request: Request,
    room_name: str,
    csrf_token: str = Form(...),
):
    """Pin a room for quick access"""
    await verify_csrf_token(request)
    annotations.pin_room(room_name)
    audit_log.log_action("room.pin", room_name, user=get_current_user(request) or "admin")
    if request.headers.get("HX-Request"):
        return Response(content="", status_code=204)
    return RedirectResponse(url="/rooms", status_code=303)


@router.post("/rooms/{room_name}/unpin", dependencies=[Depends(requires_admin)])
async def unpin_room(
    request: Request,
    room_name: str,
    csrf_token: str = Form(...),
):
    """Unpin a room"""
    await verify_csrf_token(request)
    annotations.unpin_room(room_name)
    audit_log.log_action("room.unpin", room_name, user=get_current_user(request) or "admin")
    if request.headers.get("HX-Request"):
        return Response(content="", status_code=204)
    return RedirectResponse(url="/rooms", status_code=303)


@router.post("/rooms/{room_name}/annotate", dependencies=[Depends(requires_admin)])
async def annotate_room(
    request: Request,
    room_name: str,
    csrf_token: str = Form(...),
    note: str = Form(""),
    tags: List[str] = Form([]),
):
    """Save notes and tags for a room"""
    await verify_csrf_token(request)
    annotations.set_annotations(room_name, note, tags)
    audit_log.log_action("room.annotate", room_name, user=get_current_user(request) or "admin",
                         details={"tags": tags, "note": note[:80] if note else ""})
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
