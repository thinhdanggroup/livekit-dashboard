"""JSON file-backed report rules with due-check scheduling logic."""

import json
import os
import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional


_STORE_PATH = os.environ.get("REPORT_RULES_FILE", "/tmp/report_rules.json")

SCHEDULE_TYPES = ["interval", "daily"]

_DAILY_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass
class ReportRule:
    id: str
    name: str
    schedule_type: str  # "interval" | "daily"
    interval_minutes: Optional[int] = None
    daily_time: Optional[str] = None  # "HH:MM", 24h, UTC
    enabled: bool = True
    last_run: str = ""  # ISO timestamp, UTC, or "" if never run

    def as_dict(self) -> dict:
        return asdict(self)


def _load() -> list:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(rules: list) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(rules, f, indent=2)


def list_rules() -> list[ReportRule]:
    return [ReportRule(**r) for r in _load()]


def get_rule(rule_id: str) -> Optional[ReportRule]:
    for r in _load():
        if r["id"] == rule_id:
            return ReportRule(**r)
    return None


def create_rule(
    name: str,
    schedule_type: str,
    interval_minutes: Optional[int] = None,
    daily_time: Optional[str] = None,
) -> ReportRule:
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(f"Unknown schedule_type: {schedule_type!r}")

    if schedule_type == "interval":
        if (
            not isinstance(interval_minutes, int)
            or isinstance(interval_minutes, bool)
            or interval_minutes <= 0
        ):
            raise ValueError(f"interval_minutes must be a positive int: {interval_minutes!r}")

    if schedule_type == "daily":
        if not daily_time or not _DAILY_TIME_RE.match(daily_time):
            raise ValueError(f"daily_time must be in HH:MM format: {daily_time!r}")
        try:
            datetime.strptime(daily_time, "%H:%M")
        except ValueError:
            raise ValueError(f"daily_time must be a valid HH:MM time: {daily_time!r}")

    rules = _load()
    rule = ReportRule(
        id=str(uuid.uuid4())[:8],
        name=name.strip(),
        schedule_type=schedule_type,
        interval_minutes=interval_minutes,
        daily_time=daily_time,
        enabled=True,
        last_run="",
    )
    rules.append(rule.as_dict())
    _save(rules)
    return rule


def delete_rule(rule_id: str) -> bool:
    rules = _load()
    new_rules = [r for r in rules if r["id"] != rule_id]
    if len(new_rules) == len(rules):
        return False
    _save(new_rules)
    return True


def toggle_rule(rule_id: str) -> Optional[bool]:
    """Flip enabled/disabled. Returns new enabled state, or None if not found."""
    rules = _load()
    for r in rules:
        if r["id"] == rule_id:
            r["enabled"] = not r.get("enabled", True)
            _save(rules)
            return r["enabled"]
    return None


def is_due(rule: ReportRule, now: datetime) -> bool:
    """Return True if *rule* should fire at time *now*."""
    if not rule.enabled:
        return False

    if rule.schedule_type == "interval":
        if rule.last_run == "":
            return True
        elapsed = now - datetime.fromisoformat(rule.last_run)
        return elapsed >= timedelta(minutes=rule.interval_minutes)

    if rule.schedule_type == "daily":
        past_target = now.strftime("%H:%M") >= rule.daily_time
        not_run_today = (
            rule.last_run == "" or datetime.fromisoformat(rule.last_run).date() != now.date()
        )
        return past_target and not_run_today

    return False


def mark_run(rule_id: str, now_iso: str) -> None:
    rules = _load()
    for r in rules:
        if r["id"] == rule_id:
            r["last_run"] = now_iso
            _save(rules)
            return
