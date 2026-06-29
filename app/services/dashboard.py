"""Reusable dashboard data layer.

Consolidates common analytics calls, shapes responses consistently, and
provides empty-state defaults so every view can render even when the
LiveKit API is unavailable.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.services.livekit import LiveKitClient


@dataclass
class DashboardStats:
    """Top-line metrics for the overview panel and summary cards."""

    rooms_total: int = 0
    rooms_active: int = 0
    participants_total: int = 0
    egress_active: int = 0
    ingress_active: int = 0
    connection_success_pct: float = 0.0
    connection_minutes: int = 0
    platforms: dict[str, int] = field(default_factory=dict)
    connection_types: dict[str, int] = field(default_factory=dict)
    api_latency_ms: float = 0.0
    sip_enabled: bool = False
    sip_trunks: int = 0
    error: str | None = None


async def gather_dashboard_stats(lk: LiveKitClient) -> DashboardStats:
    """Return shaped top-line stats, never raising.

    Falls back to zero-values on LiveKit errors so the UI always renders.
    Individual sub-queries that fail are silently skipped — only the
    rooms call is treated as fatal since every other stat depends on it.
    """
    stats = DashboardStats(sip_enabled=lk.sip_enabled)

    try:
        rooms, latency = await lk.list_rooms()
        stats.rooms_total = len(rooms)
        stats.rooms_active = sum(1 for r in rooms if getattr(r, "num_participants", 0) > 0)
        stats.api_latency_ms = round(latency * 1000, 1)
    except Exception as exc:
        stats.error = str(exc)
        return stats

    # Run all independent sub-queries concurrently.
    tasks = [
        lk.get_all_participants_across_rooms(),
        lk.get_egress_analytics(),
        lk.get_ingress_analytics(),
        lk.get_enhanced_analytics(),
    ]
    if lk.sip_enabled:
        tasks.append(lk.get_sip_analytics())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    participants_res, egress_res, ingress_res, enhanced_res = results[:4]

    if not isinstance(participants_res, Exception):
        stats.participants_total = len(participants_res)

    if not isinstance(egress_res, Exception):
        stats.egress_active = egress_res.get("active_jobs", 0)

    if not isinstance(ingress_res, Exception):
        stats.ingress_active = ingress_res.get("active_ingress", 0)

    if not isinstance(enhanced_res, Exception):
        stats.connection_success_pct = float(enhanced_res.get("connection_success", 0.0))
        stats.connection_minutes = int(enhanced_res.get("connection_minutes", 0))
        stats.platforms = enhanced_res.get("platforms", {})
        stats.connection_types = enhanced_res.get("connection_types", {})

    if lk.sip_enabled and len(results) > 4 and not isinstance(results[4], Exception):
        stats.sip_trunks = results[4].get("total_trunks", 0)

    return stats


def empty_room_stats() -> dict[str, Any]:
    """Zero-value room analytics dict matching get_room_analytics() shape."""
    return {
        "total_rooms": 0,
        "active_rooms": 0,
        "empty_rooms": 0,
        "total_participants": 0,
        "max_participants_room": None,
    }


def empty_egress_stats() -> dict[str, Any]:
    """Zero-value egress analytics dict matching get_egress_analytics() shape."""
    return {
        "active_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "success_rate": 100,
        "egress_types": {"room_composite": 0, "participant": 0, "track": 0, "web": 0},
        "storage_used_gb": 0,
        "total_jobs_today": 0,
    }


def empty_ingress_stats() -> dict[str, Any]:
    """Zero-value ingress analytics dict matching get_ingress_analytics() shape."""
    return {
        "total_ingress": 0,
        "active_ingress": 0,
        "ingress_types": {"rtmp": 0, "whip": 0, "url": 0},
        "avg_bitrate_mbps": 0,
        "connection_stability": 0,
        "streams_today": 0,
    }
