"""Diagnostics routes — support bundle export and webhook tester."""

import json
import urllib.request
import urllib.error
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.encoders import jsonable_encoder
from typing import Optional

from app.services.livekit import LiveKitClient, get_livekit_client
from app.services import room_annotations as annotations
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/diagnostics", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def diagnostics_index(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "diagnostics/index.html.j2",
        {
            "request": request,
            "current_user": get_current_user(request),
            "csrf_token": get_csrf_token(request),
            "webhook_result": None,
        },
    )


@router.get(
    "/diagnostics/rooms/{room_name}/bundle.json",
    dependencies=[Depends(requires_admin)],
)
async def room_support_bundle(
    request: Request,
    room_name: str,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Download a full support bundle for a room as JSON."""
    rooms, latency_ms = await lk.list_rooms(names=[room_name])
    room = rooms[0] if rooms else None

    participants = []
    try:
        raw_participants = await lk.list_participants(room_name)
        for p in raw_participants:
            participants.append({
                "identity": getattr(p, "identity", ""),
                "name": getattr(p, "name", ""),
                "joined_at": getattr(p, "joined_at", None),
                "state": str(getattr(p, "state", "")),
                "tracks": [
                    {
                        "sid": getattr(t, "sid", ""),
                        "type": getattr(t, "type", 0),
                        "muted": getattr(t, "muted", False),
                    }
                    for t in getattr(p, "tracks", [])
                ],
                "metadata": getattr(p, "metadata", ""),
            })
    except Exception:
        pass

    room_ann = annotations.get_annotations(room_name)
    timeline = annotations.build_timeline(room, raw_participants if participants else [])

    bundle = {
        "room_name": room_name,
        "api_latency_ms": round(latency_ms * 1000, 2),
        "room": {
            "name": getattr(room, "name", room_name),
            "num_participants": getattr(room, "num_participants", 0),
            "max_participants": getattr(room, "max_participants", 0),
            "creation_time": getattr(room, "creation_time", None),
            "empty_timeout": getattr(room, "empty_timeout", 0),
            "metadata": getattr(room, "metadata", ""),
        } if room else None,
        "participants": participants,
        "annotations": room_ann,
        "timeline": timeline,
    }

    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f"attachment; filename=bundle-{room_name}.json"},
    )


@router.post("/diagnostics/webhook-test", dependencies=[Depends(requires_admin)])
async def test_webhook(
    request: Request,
    csrf_token: str = Form(...),
    url: str = Form(...),
    payload: str = Form('{"event": "test", "source": "livekit-dashboard"}'),
):
    """Send a test POST to *url* with *payload* and return the response."""
    await verify_csrf_token(request)

    result: dict = {}
    try:
        body = json.loads(payload).encode() if payload.strip() else b"{}"
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "livekit-dashboard/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = {
                "status": resp.status,
                "reason": resp.reason,
                "body": resp.read(512).decode(errors="replace"),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        result = {"status": e.code, "reason": e.reason, "body": e.read(256).decode(errors="replace"), "error": None}
    except Exception as exc:
        result = {"status": None, "reason": None, "body": "", "error": str(exc)}

    return request.app.state.templates.TemplateResponse(
        request,
        "diagnostics/index.html.j2",
        {
            "request": request,
            "current_user": get_current_user(request),
            "csrf_token": get_csrf_token(request),
            "webhook_result": result,
            "webhook_url": url,
            "webhook_payload": payload,
        },
    )
