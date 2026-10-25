"""Diagnostics routes — support bundle export and webhook tester."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.encoders import jsonable_encoder
from typing import Optional

import app.utils.http as http_util
from app.services.livekit import LiveKitClient, get_livekit_client
from app.services import room_annotations as annotations
from app.services import webhook_log
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
            "webhook_log_entries": webhook_log.list_entries(limit=50),
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

    result = http_util.post_json(url, payload)
    webhook_log.log_delivery("manual_test", url, payload, result.get("status"), result.get("error"))

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
            "webhook_log_entries": webhook_log.list_entries(limit=50),
        },
    )


@router.post("/diagnostics/webhook-log/{entry_id}/replay", dependencies=[Depends(requires_admin)])
async def replay_webhook(request: Request, entry_id: str, csrf_token: str = Form(...)):
    """Re-send a previously logged webhook delivery by its log entry id."""
    await verify_csrf_token(request)

    entry = webhook_log.get_entry(entry_id)
    if entry is None:
        return RedirectResponse(url="/diagnostics", status_code=303)

    result = http_util.post_json(entry["url"], entry["payload"])
    webhook_log.log_delivery("replay", entry["url"], entry["payload"], result.get("status"), result.get("error"))

    return RedirectResponse(url="/diagnostics", status_code=303)
