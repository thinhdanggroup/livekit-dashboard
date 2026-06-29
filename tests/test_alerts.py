"""Tests for alert rules service and routes."""

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch


def _csrf():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


# ---------------------------------------------------------------------------
# Minimal stats stub
# ---------------------------------------------------------------------------

@dataclass
class _Stats:
    rooms_total: int = 0
    rooms_active: int = 0
    participants_total: int = 0
    egress_active: int = 0
    ingress_active: int = 0
    api_latency_ms: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

def test_list_rules_empty(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        assert al.list_rules() == []


def test_create_rule_basic(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        rule = al.create_rule(name="High rooms", metric="rooms_total", operator=">", threshold=50)
    assert rule.name == "High rooms"
    assert rule.metric == "rooms_total"
    assert rule.threshold == 50.0
    assert rule.enabled is True


def test_create_rule_invalid_metric(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        with pytest.raises(ValueError):
            al.create_rule(name="bad", metric="nonexistent", operator=">", threshold=1)


def test_create_rule_invalid_operator(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        with pytest.raises(ValueError):
            al.create_rule(name="bad", metric="rooms_total", operator="!=", threshold=1)


def test_create_rule_invalid_severity(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        with pytest.raises(ValueError):
            al.create_rule(name="bad", metric="rooms_total", operator=">", threshold=1, severity="info")


def test_delete_rule(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        rule = al.create_rule(name="Delete me", metric="rooms_total", operator=">", threshold=0)
        result = al.delete_rule(rule.id)
        remaining = al.list_rules()
    assert result is True
    assert remaining == []


def test_delete_rule_not_found(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        assert al.delete_rule("bad-id") is False


def test_toggle_rule(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        rule = al.create_rule(name="Toggle", metric="rooms_total", operator=">", threshold=0)
        assert rule.enabled is True
        new_state = al.toggle_rule(rule.id)
        assert new_state is False
        toggled_back = al.toggle_rule(rule.id)
        assert toggled_back is True


def test_toggle_rule_not_found(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        assert al.toggle_rule("nonexistent") is None


@pytest.mark.parametrize("op,value,threshold,expected", [
    (">", 10, 5, True),
    (">", 5, 10, False),
    (">=", 5, 5, True),
    ("<", 3, 5, True),
    ("<=", 5, 5, True),
    ("<", 10, 5, False),
])
def test_rule_evaluate(op, value, threshold, expected):
    from app.services.alerts import AlertRule
    rule = AlertRule(id="x", name="t", metric="rooms_total", operator=op, threshold=threshold)
    assert rule.evaluate(_Stats(rooms_total=value)) is expected


def test_rule_evaluate_disabled():
    from app.services.alerts import AlertRule
    rule = AlertRule(id="x", name="t", metric="rooms_total", operator=">", threshold=0, enabled=False)
    assert rule.evaluate(_Stats(rooms_total=999)) is False


def test_rule_evaluate_unknown_metric():
    from app.services.alerts import AlertRule
    rule = AlertRule(id="x", name="t", metric="nonexistent", operator=">", threshold=0)
    assert rule.evaluate(_Stats()) is False


def test_evaluate_all(tmp_path):
    import app.services.alerts as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        al.create_rule(name="High latency", metric="api_latency_ms", operator=">", threshold=100)
        al.create_rule(name="No rooms", metric="rooms_total", operator=">", threshold=0)
        stats = _Stats(api_latency_ms=200.0, rooms_total=0)
        results = al.evaluate_all(stats)
    triggered = {r.name: t for r, t in results}
    assert triggered["High latency"] is True
    assert triggered["No rooms"] is False


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_alerts_page_requires_auth(client):
    resp = client.get("/alerts", follow_redirects=False)
    assert resp.status_code == 401


def test_alerts_page_returns_200(client, auth_headers, tmp_path):
    import app.services.alerts as al
    from app.services.dashboard import DashboardStats

    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")), \
         patch("app.routes.alerts.gather_dashboard_stats", new=AsyncMock(return_value=DashboardStats())):
        resp = client.get("/alerts", headers=auth_headers)
    assert resp.status_code == 200
    assert b"Alert Rules" in resp.content


def test_create_alert_via_route(client, auth_headers, tmp_path):
    import app.services.alerts as al
    from app.services.dashboard import DashboardStats

    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")), \
         patch("app.routes.alerts.gather_dashboard_stats", new=AsyncMock(return_value=DashboardStats())):
        resp = client.post(
            "/alerts",
            data={
                "csrf_token": _csrf(),
                "name": "Test alert",
                "metric": "rooms_total",
                "operator": ">",
                "threshold": "5",
                "severity": "warning",
            },
            headers=auth_headers,
            follow_redirects=False,
        )
    assert resp.status_code == 303


def test_delete_alert_via_route(client, auth_headers, tmp_path):
    import app.services.alerts as al
    from app.services.dashboard import DashboardStats

    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        rule = al.create_rule(name="Delete route", metric="rooms_total", operator=">", threshold=0)
        resp = client.post(
            f"/alerts/{rule.id}/delete",
            data={"csrf_token": _csrf()},
            headers=auth_headers,
            follow_redirects=False,
        )
    assert resp.status_code == 303


def test_toggle_alert_via_route(client, auth_headers, tmp_path):
    import app.services.alerts as al

    with patch.object(al, "_STORE_PATH", str(tmp_path / "alerts.json")):
        rule = al.create_rule(name="Toggle route", metric="rooms_total", operator=">", threshold=0)
        resp = client.post(
            f"/alerts/{rule.id}/toggle",
            data={"csrf_token": _csrf()},
            headers=auth_headers,
            follow_redirects=False,
        )
    assert resp.status_code == 303
