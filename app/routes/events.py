"""Live event stream via Server-Sent Events."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.security.basic_auth import requires_admin
from app.services.livekit import LiveKitClient, get_livekit_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events")

_POLL_INTERVAL = 5  # seconds between LiveKit polls


async def _sse_generator(lk: LiveKitClient):
    """Yield SSE events by polling LiveKit and diffing room/participant state."""
    known_rooms: dict[str, set[str]] = {}  # room_name -> set of participant identities

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _event(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n"

    # Initial keepalive so the browser EventSource doesn't timeout immediately
    yield ": keepalive\n\n"

    while True:
        try:
            rooms, _ = await lk.list_rooms()
            current_rooms: dict[str, set[str]] = {}

            for room in rooms:
                name = room.name
                participants = await lk.list_participants(name)
                identities = {p.identity for p in participants}
                current_rooms[name] = identities

                if name not in known_rooms:
                    # New room appeared
                    yield _event("room.created", {
                        "room": name,
                        "participants": len(identities),
                        "ts": _now(),
                    })
                else:
                    # Check participant changes
                    joined = identities - known_rooms[name]
                    left = known_rooms[name] - identities
                    for identity in joined:
                        yield _event("participant.joined", {
                            "room": name,
                            "identity": identity,
                            "ts": _now(),
                        })
                    for identity in left:
                        yield _event("participant.left", {
                            "room": name,
                            "identity": identity,
                            "ts": _now(),
                        })

            # Rooms that disappeared
            for name in known_rooms:
                if name not in current_rooms:
                    yield _event("room.closed", {"room": name, "ts": _now()})

            known_rooms = current_rooms

        except Exception as exc:
            logger.warning("SSE poll error: %s", exc)
            yield _event("error", {"message": str(exc), "ts": _now()})

        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/stream")
async def events_stream(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """SSE endpoint — yields room/participant change events every 5 s."""
    return StreamingResponse(
        _sse_generator(lk),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def events_page(request: Request):
    """Live event feed page."""
    return request.app.state.templates.TemplateResponse(
        request,
        "events/index.html.j2",
        {"request": request},
    )
