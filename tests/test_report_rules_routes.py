"""Tests for report rule management routes."""

from unittest.mock import AsyncMock, MagicMock

import app.services.report_rules as rr
from app.services import notifications, webhook_log
from app.services.dashboard import DashboardStats


def _csrf():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


def test_reports_page_requires_auth(client):
    resp = client.get("/reports", follow_redirects=False)
    assert resp.status_code == 401


def test_create_and_list_report_rule(client, auth_headers):
    client.post(
        "/reports",
        headers=auth_headers,
        data={
            "csrf_token": _csrf(),
            "name": "Daily Digest",
            "schedule_type": "daily",
            "interval_minutes": "",
            "daily_time": "09:00",
        },
    )
    resp = client.get("/reports", headers=auth_headers)
    assert resp.status_code == 200
    assert b"Daily Digest" in resp.content


def test_create_report_rule_invalid_input_does_not_500(client, auth_headers):
    resp = client.post(
        "/reports",
        headers=auth_headers,
        data={
            "csrf_token": _csrf(),
            "name": "bad",
            "schedule_type": "weekly",
            "interval_minutes": "",
            "daily_time": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert rr.list_rules() == []


def test_toggle_and_delete_report_rule(client, auth_headers):
    client.post(
        "/reports",
        headers=auth_headers,
        data={
            "csrf_token": _csrf(),
            "name": "x",
            "schedule_type": "interval",
            "interval_minutes": "60",
            "daily_time": "",
        },
    )
    rule_id = rr.list_rules()[0].id

    resp = client.post(
        f"/reports/{rule_id}/toggle",
        headers=auth_headers,
        data={"csrf_token": _csrf()},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert rr.get_rule(rule_id).enabled is False

    resp = client.post(
        f"/reports/{rule_id}/delete",
        headers=auth_headers,
        data={"csrf_token": _csrf()},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert rr.get_rule(rule_id) is None


def test_run_now_fires_regardless_of_schedule(client, auth_headers, monkeypatch):
    from datetime import datetime, timezone

    notifications.save_config(webhook_url="http://example.com/hook")
    rule = rr.create_rule("Not due yet", "interval", interval_minutes=999999)
    rr.mark_run(rule.id, "2026-01-01T00:00:00+00:00")
    rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is False

    monkeypatch.setattr(
        "app.utils.http.post_json",
        MagicMock(return_value={"status": 200, "body": "", "error": None}),
    )
    monkeypatch.setattr(
        "app.services.dashboard.gather_dashboard_stats",
        AsyncMock(return_value=DashboardStats(rooms_total=1, rooms_active=1)),
    )

    resp = client.post(
        f"/reports/{rule.id}/run-now",
        headers=auth_headers,
        data={"csrf_token": _csrf()},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    entries = webhook_log.list_entries()
    assert len(entries) == 1
    assert entries[0]["source"] == "report_rule"
    assert entries[0]["status"] == 200

    updated = rr.get_rule(rule.id)
    assert updated.last_run != "2026-01-01T00:00:00+00:00"


def test_run_now_unknown_rule_id_redirects_without_error(client, auth_headers):
    resp = client.post(
        "/reports/does-not-exist/run-now",
        headers=auth_headers,
        data={"csrf_token": _csrf()},
        follow_redirects=False,
    )
    assert resp.status_code == 303
