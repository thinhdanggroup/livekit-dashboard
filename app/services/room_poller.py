"""Background poller that ticks against every live room on a fixed interval,
feeding both the ghost-rooms tracker (rooms that vanished between polls) and
the per-room lifecycle history store (participant joins/leaves/mutes).

This mirrors, rather than reuses, the ghost-rooms snapshot-building logic in
`app/routes/rooms.py`'s `rooms_index` route: both need the exact same shape,
and both independently skip tracking when `list_rooms()` fails so a
transient LiveKit API error never fabricates "every room just closed".
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.services import ghost_rooms, room_history
from app.services.livekit import LiveKitClient

logger = logging.getLogger(__name__)

# Module-level last-known per-room participant state, keyed by room name.
# Lives at module scope (same precedent as app/services/cache.py's _store)
# so it survives across ticks of the poller loop.
_last_known: dict[str, dict] = {}


def _reset_for_tests() -> None:
    """Clear in-memory poller state between tests."""
    global _last_known
    _last_known = {}


def _label_for(event: dict) -> str:
    """Build a human-readable label for a diff_room_state event."""
    if not event["identity"]:
        return event["kind"]
    verb = event["kind"].replace("participant_", "").replace("track_", "")
    return f"{event['identity']} {verb}"


async def poll_once(lk: LiveKitClient) -> None:
    """Fetch live rooms, update ghost tracking, and record lifecycle events
    for each room's participant state. Any failure to list rooms propagates
    to the caller (run_poller_loop), which already wraps the whole tick."""
    now = datetime.now(timezone.utc)
    rooms, _ = await lk.list_rooms()

    snapshot = [
        {
            "name": r.name,
            "num_participants": getattr(r, "num_participants", 0),
            "max_participants": getattr(r, "max_participants", 0),
            "creation_time": getattr(r, "creation_time", 0),
            "metadata": getattr(r, "metadata", ""),
        }
        for r in rooms
    ]
    ghost_rooms.record_poll(snapshot)

    current_names = set()
    for room in rooms:
        current_names.add(room.name)
        try:
            participants = await lk.list_participants(room.name)
            curr_state = {
                "participants": {
                    p.identity: {
                        "muted_tracks": {t.sid for t in p.tracks if getattr(t, "muted", False)}
                    }
                    for p in participants
                }
            }
            prev_state = _last_known.get(room.name)
            if prev_state is None:
                room_history.append_event(room.name, "room_created", "Room created")

            events, new_state = room_history.diff_room_state(prev_state, curr_state)
            for event in events:
                room_history.append_event(
                    room.name, event["kind"], _label_for(event), identity=event["identity"]
                )

            _last_known[room.name] = new_state
            room_history.mark_seen(room.name, now)
        except Exception:
            logger.warning(
                "room_poller: failed to poll room %s; skipping it this tick",
                room.name,
                exc_info=True,
            )
            continue

    # A room no longer present is dropped from in-memory state so that if it
    # reappears later (same name) it's treated as a fresh sighting, not a
    # continuation of the prior session. No "room_ended" event is synthesized
    # here -- the ghost-rooms row already communicates that visually.
    for name in list(_last_known.keys()):
        if name not in current_names:
            del _last_known[name]

    room_history.prune_old(now)


async def run_poller_loop(interval_seconds: int = 5) -> None:
    """Tick poll_once() forever, swallowing any error so one bad tick never
    kills the background task."""
    while True:
        lk = None
        try:
            lk = LiveKitClient()
            await poll_once(lk)
        except Exception as exc:
            logger.warning("room poller tick failed: %s", exc, exc_info=True)
        finally:
            # LiveKitClient lazily opens an aiohttp session on first use; a
            # fresh client is created every tick, so it must be closed every
            # tick too or each 5-second poll leaks one.
            if lk is not None:
                try:
                    await lk.close()
                except Exception:
                    pass
        await asyncio.sleep(interval_seconds)
