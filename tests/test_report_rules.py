"""Tests for report rule store and due-check logic."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app.services.report_rules as rr


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
