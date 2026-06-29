"""Tests for anomaly detection heuristics."""

import pytest
from dataclasses import dataclass


@dataclass
class _Stats:
    rooms_total: int = 0
    rooms_active: int = 0
    participants_total: int = 0
    egress_active: int = 0
    ingress_active: int = 0
    sip_trunks: int = 0
    api_latency_ms: float = 0.0
    error: str = ""


from app.services.anomaly import detect


def test_no_anomalies_baseline():
    stats = _Stats(rooms_total=3, rooms_active=2, participants_total=10, api_latency_ms=50.0)
    obs = detect(stats)
    assert obs == []


def test_critical_latency():
    stats = _Stats(api_latency_ms=600.0)
    obs = detect(stats)
    titles = [o.title for o in obs]
    assert any("latency" in t.lower() for t in titles)
    severities = [o.severity for o in obs]
    assert "critical" in severities


def test_warning_latency():
    stats = _Stats(api_latency_ms=250.0)
    obs = detect(stats)
    assert any(o.severity == "warning" and "latency" in o.title.lower() for o in obs)


def test_normal_latency_no_flag():
    obs = detect(_Stats(api_latency_ms=150.0))
    assert not any("latency" in o.title.lower() for o in obs)


def test_all_rooms_empty():
    stats = _Stats(rooms_total=5, rooms_active=0, participants_total=0)
    obs = detect(stats)
    assert any("empty" in o.title.lower() for o in obs)


def test_rooms_total_zero_no_empty_flag():
    obs = detect(_Stats(rooms_total=0, rooms_active=0))
    assert not any("empty" in o.title.lower() for o in obs)


def test_high_avg_participants():
    stats = _Stats(rooms_active=2, participants_total=250)
    obs = detect(stats)
    assert any("participant" in o.title.lower() for o in obs)


def test_normal_participant_count_no_flag():
    obs = detect(_Stats(rooms_active=5, participants_total=50))
    assert not any("participant" in o.title.lower() for o in obs)


def test_many_egress_jobs():
    obs = detect(_Stats(egress_active=25))
    assert any("egress" in o.title.lower() for o in obs)


def test_error_stats_returns_empty():
    obs = detect(_Stats(error="connection refused"))
    assert obs == []
