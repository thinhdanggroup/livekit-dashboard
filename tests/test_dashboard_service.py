"""Tests for app.services.dashboard"""
from unittest.mock import AsyncMock, MagicMock

from app.services.dashboard import (
    DashboardStats,
    empty_egress_stats,
    empty_ingress_stats,
    empty_room_stats,
    gather_dashboard_stats,
)


def _make_lk(**overrides):
    """Return a minimal mock LiveKitClient with all async analytics methods stubbed."""
    lk = MagicMock()
    lk.sip_enabled = False
    lk.list_rooms = AsyncMock(return_value=([], 0.01))
    lk.get_all_participants_across_rooms = AsyncMock(return_value=[])
    lk.get_egress_analytics = AsyncMock(return_value={"active_jobs": 0})
    lk.get_ingress_analytics = AsyncMock(return_value={"active_ingress": 0})
    lk.get_sip_analytics = AsyncMock(return_value={"total_trunks": 0})
    lk.get_enhanced_analytics = AsyncMock(
        return_value={
            "connection_success": 100.0,
            "connection_minutes": 0,
            "platforms": {},
            "connection_types": {},
        }
    )
    for k, v in overrides.items():
        setattr(lk, k, v)
    return lk


async def test_gather_stats_empty_server():
    stats = await gather_dashboard_stats(_make_lk())
    assert isinstance(stats, DashboardStats)
    assert stats.rooms_total == 0
    assert stats.participants_total == 0
    assert stats.egress_active == 0
    assert stats.ingress_active == 0
    assert stats.error is None


async def test_gather_stats_room_counts():
    room_a = MagicMock(num_participants=3)
    room_b = MagicMock(num_participants=0)
    lk = _make_lk(
        list_rooms=AsyncMock(return_value=([room_a, room_b], 0.025)),
        get_all_participants_across_rooms=AsyncMock(
            return_value=[MagicMock(), MagicMock(), MagicMock()]
        ),
    )
    stats = await gather_dashboard_stats(lk)
    assert stats.rooms_total == 2
    assert stats.rooms_active == 1
    assert stats.participants_total == 3
    assert stats.api_latency_ms == 25.0


async def test_gather_stats_egress_ingress_active():
    lk = _make_lk(
        get_egress_analytics=AsyncMock(return_value={"active_jobs": 2}),
        get_ingress_analytics=AsyncMock(return_value={"active_ingress": 1}),
    )
    stats = await gather_dashboard_stats(lk)
    assert stats.egress_active == 2
    assert stats.ingress_active == 1


async def test_gather_stats_sip_trunks():
    lk = _make_lk(get_sip_analytics=AsyncMock(return_value={"total_trunks": 4}))
    lk.sip_enabled = True
    stats = await gather_dashboard_stats(lk)
    assert stats.sip_enabled is True
    assert stats.sip_trunks == 4


async def test_gather_stats_sip_not_queried_when_disabled():
    lk = _make_lk()
    lk.sip_enabled = False
    stats = await gather_dashboard_stats(lk)
    lk.get_sip_analytics.assert_not_called()
    assert stats.sip_trunks == 0


async def test_gather_stats_rooms_error_is_fatal():
    lk = _make_lk(list_rooms=AsyncMock(side_effect=Exception("connection refused")))
    stats = await gather_dashboard_stats(lk)
    assert stats.error == "connection refused"
    assert stats.rooms_total == 0
    # downstream calls should not have been made
    lk.get_all_participants_across_rooms.assert_not_called()


async def test_gather_stats_partial_failure_skipped():
    """Participant and analytics failures don't poison the whole result."""
    lk = _make_lk(
        get_all_participants_across_rooms=AsyncMock(side_effect=Exception("timeout")),
        get_enhanced_analytics=AsyncMock(side_effect=Exception("analytics down")),
    )
    stats = await gather_dashboard_stats(lk)
    assert stats.error is None
    assert stats.participants_total == 0
    assert stats.connection_success_pct == 0.0


async def test_gather_stats_connection_analytics():
    lk = _make_lk(
        get_enhanced_analytics=AsyncMock(
            return_value={
                "connection_success": 97.3,
                "connection_minutes": 1500,
                "platforms": {"Web": 10, "iOS": 2},
                "connection_types": {"WebRTC": 12},
            }
        )
    )
    stats = await gather_dashboard_stats(lk)
    assert stats.connection_success_pct == 97.3
    assert stats.connection_minutes == 1500
    assert stats.platforms == {"Web": 10, "iOS": 2}


def test_empty_room_stats_shape():
    s = empty_room_stats()
    assert s["total_rooms"] == 0
    assert "active_rooms" in s


def test_empty_egress_stats_shape():
    s = empty_egress_stats()
    assert s["active_jobs"] == 0
    assert s["success_rate"] == 100
    assert "egress_types" in s


def test_empty_ingress_stats_shape():
    s = empty_ingress_stats()
    assert s["total_ingress"] == 0
    assert s["active_ingress"] == 0
