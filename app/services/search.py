"""Global cross-entity search.

Fetches rooms, participants, egress jobs, and ingress streams concurrently
and returns a flat list of SearchResult items matching the query string.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """A single search hit with enough context to render a result row."""

    kind: str   # "room" | "participant" | "egress" | "ingress"
    title: str
    subtitle: str
    url: str
    status: str = ""


def _matches(q: str, *fields: str) -> bool:
    """Return True if q appears (case-insensitive) in any of the given fields."""
    ql = q.lower()
    return any(ql in (f or "").lower() for f in fields)


async def _search_rooms(lk, q: str) -> list[SearchResult]:
    try:
        rooms, _ = await lk.list_rooms()
    except Exception:
        return []
    out: list[SearchResult] = []
    for room in rooms:
        name = getattr(room, "name", "") or ""
        meta = getattr(room, "metadata", "") or ""
        if not _matches(q, name, meta):
            continue
        n = getattr(room, "num_participants", 0) or 0
        status = "active" if n > 0 else "idle"
        out.append(
            SearchResult(
                kind="room",
                title=name,
                subtitle=f"{n} participant{'s' if n != 1 else ''}",
                url=f"/rooms/{name}",
                status=status,
            )
        )
    return out


async def _search_participants(lk, q: str) -> list[SearchResult]:
    try:
        participants = await lk.get_all_participants_across_rooms()
    except Exception:
        return []
    out: list[SearchResult] = []
    for p in participants:
        identity = getattr(p, "identity", "") or ""
        name = getattr(p, "name", "") or ""
        meta = getattr(p, "metadata", "") or ""
        room_name = getattr(p, "_room_name", "") or ""
        if not _matches(q, identity, name, meta, room_name):
            continue
        display = name if name else identity
        out.append(
            SearchResult(
                kind="participant",
                title=display,
                subtitle=f"in {room_name}" if room_name else identity,
                url=f"/rooms/{room_name}" if room_name else "/rooms",
                status="connected",
            )
        )
    return out


async def _search_egress(lk, q: str) -> list[SearchResult]:
    try:
        jobs = await lk.list_egress(active=False)
    except Exception:
        return []
    out: list[SearchResult] = []
    for job in jobs:
        egress_id = getattr(job, "egress_id", "") or ""
        room_name = getattr(job, "room_name", "") or ""
        if not _matches(q, egress_id, room_name):
            continue
        out.append(
            SearchResult(
                kind="egress",
                title=egress_id,
                subtitle=f"room: {room_name}" if room_name else "recording job",
                url="/egress",
                status="active",
            )
        )
    return out


async def _search_ingress(lk, q: str) -> list[SearchResult]:
    try:
        streams = await lk.list_ingress()
    except Exception:
        return []
    out: list[SearchResult] = []
    for stream in streams:
        ingress_id = getattr(stream, "ingress_id", "") or ""
        name = getattr(stream, "name", "") or ""
        room_name = getattr(stream, "room_name", "") or ""
        url = getattr(stream, "url", "") or ""
        if not _matches(q, ingress_id, name, room_name, url):
            continue
        display = name if name else ingress_id
        out.append(
            SearchResult(
                kind="ingress",
                title=display,
                subtitle=f"room: {room_name}" if room_name else "ingress stream",
                url="/ingress",
                status="active",
            )
        )
    return out


async def search_all(lk, q: str) -> list[SearchResult]:
    """Search rooms, participants, egress, and ingress for *q*.

    Returns an empty list immediately when *q* is blank.
    Partial API failures return empty results for that entity type only.
    """
    if not q or not q.strip():
        return []

    batches = await asyncio.gather(
        _search_rooms(lk, q),
        _search_participants(lk, q),
        _search_egress(lk, q),
        _search_ingress(lk, q),
    )
    return [item for batch in batches for item in batch]
