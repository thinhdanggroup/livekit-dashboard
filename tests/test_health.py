"""Tests for the plain-English health summary."""

from app.services import health
from app.services.dashboard import DashboardStats


def test_evaluate_down_when_stats_has_error():
    stats = DashboardStats(error="connection refused")
    result = health.evaluate(stats)
    assert result.severity == "down"
    assert "connection refused" in result.headline


def test_evaluate_healthy_under_200ms():
    stats = DashboardStats(api_latency_ms=42.0, rooms_total=3, rooms_active=1, participants_total=2)
    result = health.evaluate(stats)
    assert result.severity == "healthy"
    assert "42" in result.headline


def test_evaluate_degraded_between_200_and_500ms():
    stats = DashboardStats(api_latency_ms=250.0)
    assert health.evaluate(stats).severity == "degraded"


def test_evaluate_down_above_500ms():
    stats = DashboardStats(api_latency_ms=600.0)
    assert health.evaluate(stats).severity == "down"


def test_evaluate_details_include_room_and_participant_counts():
    stats = DashboardStats(api_latency_ms=10.0, rooms_total=5, rooms_active=2, participants_total=7, egress_active=1, ingress_active=0)
    details = " ".join(health.evaluate(stats).details)
    assert "2" in details and "5" in details and "7" in details


def test_evaluate_omits_sip_when_disabled():
    stats = DashboardStats(api_latency_ms=10.0, sip_enabled=False, sip_trunks=3)
    details = " ".join(health.evaluate(stats).details)
    assert "SIP" not in details and "sip" not in details


def test_evaluate_includes_sip_when_enabled():
    stats = DashboardStats(api_latency_ms=10.0, sip_enabled=True, sip_trunks=2)
    details = " ".join(health.evaluate(stats).details)
    assert "2" in details and "SIP" in details
