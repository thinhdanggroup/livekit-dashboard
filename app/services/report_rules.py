"""JSON file-backed report rules with due-check scheduling logic."""

import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import app.services.dashboard as dashboard
import app.utils.http as http_util
from app.services import anomaly, notifications, webhook_log
from app.services.dashboard import DashboardStats
from app.services.livekit import LiveKitClient


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


def build_digest(rule_name: str, stats: DashboardStats, observations: list) -> str:
    """Serialize a webhook digest payload for *rule_name* from dashboard stats."""
    return json.dumps({
        "source": "livekit-dashboard",
        "report": rule_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "rooms_total": stats.rooms_total,
            "rooms_active": stats.rooms_active,
            "participants_total": stats.participants_total,
            "egress_active": stats.egress_active,
            "ingress_active": stats.ingress_active,
            "connection_success_pct": stats.connection_success_pct,
            "connection_minutes": stats.connection_minutes,
            "platforms": stats.platforms,
            "connection_types": stats.connection_types,
            "api_latency_ms": stats.api_latency_ms,
            "sip_enabled": stats.sip_enabled,
            "sip_trunks": stats.sip_trunks,
            "error": stats.error,
        },
        "observations": [asdict(o) for o in observations],
    })


async def run_rule_now(rule: ReportRule, lk: LiveKitClient) -> dict:
    """Run *rule* unconditionally: gather stats, build a digest, deliver it.

    Always marks the rule as run (even on failure) so a crashing rule
    doesn't retry on every scheduler tick.
    """
    result = {"status": None, "error": None}
    try:
        stats = await dashboard.gather_dashboard_stats(lk)
        observations = anomaly.detect(stats)
        payload = build_digest(rule.name, stats, observations)
        url = notifications.get_config().get("webhook_url", "").strip()
        if url:
            # Run the blocking (urllib-based, up to 5s timeout) POST in a
            # thread pool so it doesn't freeze the event loop -- this is
            # called from run_scheduler_loop's recurring background task,
            # and a slow/unresponsive webhook host would otherwise stall
            # every request in the app (including /health) for up to 5s.
            result = await asyncio.to_thread(http_util.post_json, url, payload)
        else:
            result = {"status": None, "error": "no webhook_url configured"}
        webhook_log.log_delivery(
            "report_rule", url, payload, result.get("status"), result.get("error")
        )
    except Exception as exc:
        result = {"status": None, "error": str(exc)}
    finally:
        mark_run(rule.id, datetime.now(timezone.utc).isoformat())
    return {"rule_id": rule.id, "status": result.get("status"), "error": result.get("error")}


async def run_due_rules(lk: LiveKitClient, now: datetime | None = None) -> list[dict]:
    """Run every enabled rule that is currently due, returning per-rule results."""
    now = now or datetime.now(timezone.utc)
    return [await run_rule_now(rule, lk) for rule in list_rules() if is_due(rule, now)]


async def run_scheduler_loop(interval_seconds: int = 60) -> None:
    """Run due report rules on a fixed interval until cancelled."""
    while True:
        try:
            await run_due_rules(LiveKitClient())
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)
