"""Tests for report rule store and due-check logic."""

import json

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.report_rules as rr
from app.services import anomaly, notifications, webhook_log
from app.services.dashboard import DashboardStats


def test_create_rule_rejects_bad_schedule_type(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        with pytest.raises(ValueError):
            rr.create_rule("x", "weekly")


def test_create_interval_rule_requires_minutes(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        with pytest.raises(ValueError):
            rr.create_rule("x", "interval", interval_minutes=0)


def test_create_daily_rule_requires_valid_time(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        with pytest.raises(ValueError):
            rr.create_rule("x", "daily", daily_time="25:99")


def test_interval_rule_due_when_never_run(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=10)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is True


def test_interval_rule_not_due_before_elapsed(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=10)
        rr.mark_run(rule.id, datetime.now(timezone.utc).isoformat())
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is False


def test_interval_rule_due_after_elapsed(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=10)
        ten_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        rr.mark_run(rule.id, ten_min_ago)
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is True


def test_daily_rule_due_once_past_target_time_then_not_again_same_day(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "daily", daily_time="00:00")  # always past target
        now = datetime.now(timezone.utc)
        assert rr.is_due(rule, now) is True
        rr.mark_run(rule.id, now.isoformat())
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, now) is False


def test_daily_rule_not_due_before_target_time(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "daily", daily_time="23:59")
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)  # before 23:59
    assert rr.is_due(rule, now) is False


def test_disabled_rule_never_due(tmp_path):
    with patch.object(rr, "_STORE_PATH", str(tmp_path / "r.json")):
        rule = rr.create_rule("x", "interval", interval_minutes=1)
        rr.toggle_rule(rule.id)  # disable
        rule = rr.get_rule(rule.id)
    assert rr.is_due(rule, datetime.now(timezone.utc)) is False


def test_build_digest_includes_stats_and_observations():
    stats = DashboardStats(rooms_total=3, rooms_active=1, api_latency_ms=42.0)
    obs = [anomaly.Observation(severity="warning", title="t", detail="d")]
    payload = json.loads(rr.build_digest("Daily Summary", stats, obs))
    assert payload["report"] == "Daily Summary"
    assert payload["stats"]["rooms_total"] == 3
    assert payload["observations"][0]["title"] == "t"


@pytest.fixture
def _report_rules_env(tmp_path, monkeypatch):
    """Point report_rules, notifications, and webhook_log stores at tmp_path."""
    monkeypatch.setattr(rr, "_STORE_PATH", str(tmp_path / "rules.json"))
    monkeypatch.setattr(notifications, "_STORE_PATH", str(tmp_path / "notifications.json"))
    monkeypatch.setattr(webhook_log, "_STORE_PATH", str(tmp_path / "webhook_log.json"))
    return tmp_path


async def test_run_due_rules_posts_and_logs(_report_rules_env, monkeypatch):
    notifications.save_config(webhook_url="http://example.com/hook")
    rule = rr.create_rule("Daily Summary", "interval", interval_minutes=1)

    monkeypatch.setattr(
        "app.utils.http.post_json",
        MagicMock(return_value={"status": 200, "body": "", "error": None}),
    )
    monkeypatch.setattr(
        "app.services.dashboard.gather_dashboard_stats",
        AsyncMock(return_value=DashboardStats(rooms_total=1, rooms_active=1)),
    )

    results = await rr.run_due_rules(lk=MagicMock())

    assert len(results) == 1
    assert results[0]["rule_id"] == rule.id
    assert results[0]["status"] == 200
    assert results[0]["error"] is None

    updated = rr.get_rule(rule.id)
    assert updated.last_run != ""

    entries = webhook_log.list_entries()
    assert len(entries) == 1
    assert entries[0]["source"] == "report_rule"
    assert entries[0]["status"] == 200


async def test_run_due_rules_logs_failure_when_no_webhook_configured(_report_rules_env, monkeypatch):
    rule = rr.create_rule("Daily Summary", "interval", interval_minutes=1)

    monkeypatch.setattr(
        "app.services.dashboard.gather_dashboard_stats",
        AsyncMock(return_value=DashboardStats(rooms_total=1, rooms_active=1)),
    )

    results = await rr.run_due_rules(lk=MagicMock())

    assert len(results) == 1
    assert results[0]["rule_id"] == rule.id
    assert results[0]["status"] is None
    assert results[0]["error"]

    updated = rr.get_rule(rule.id)
    assert updated.last_run != ""

    entries = webhook_log.list_entries()
    assert len(entries) == 1
    assert entries[0]["source"] == "report_rule"
    assert entries[0]["status"] is None
    assert entries[0]["error"]


async def test_run_due_rules_skips_not_due_and_disabled(_report_rules_env, monkeypatch):
    not_due_rule = rr.create_rule("Not Due", "interval", interval_minutes=10)
    rr.mark_run(not_due_rule.id, datetime.now(timezone.utc).isoformat())

    disabled_rule = rr.create_rule("Disabled", "interval", interval_minutes=1)
    rr.toggle_rule(disabled_rule.id)

    post_mock = MagicMock(return_value={"status": 200, "body": "", "error": None})
    monkeypatch.setattr("app.utils.http.post_json", post_mock)
    gather_mock = AsyncMock(return_value=DashboardStats())
    monkeypatch.setattr("app.services.dashboard.gather_dashboard_stats", gather_mock)

    results = await rr.run_due_rules(lk=MagicMock())

    assert results == []
    post_mock.assert_not_called()
    gather_mock.assert_not_called()


async def test_run_rule_now_marks_run_on_crash(_report_rules_env, monkeypatch):
    rule = rr.create_rule("Daily Summary", "interval", interval_minutes=1)
    assert rule.last_run == ""

    monkeypatch.setattr(
        "app.services.dashboard.gather_dashboard_stats",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    result = await rr.run_rule_now(rule, lk=MagicMock())

    assert result["status"] is None
    assert "boom" in result["error"]

    updated = rr.get_rule(rule.id)
    assert updated.last_run != ""
