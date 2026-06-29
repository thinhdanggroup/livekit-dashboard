"""JSON file-backed alert rules with threshold evaluation against dashboard stats."""

import json
import os
import uuid
from dataclasses import dataclass, asdict
from typing import Optional


_STORE_PATH = os.environ.get("ALERT_RULES_FILE", "/tmp/alert_rules.json")

METRICS: dict[str, str] = {
    "rooms_total": "Total Rooms",
    "rooms_active": "Active Rooms",
    "participants_total": "Total Participants",
    "egress_active": "Active Egress Jobs",
    "ingress_active": "Active Ingress Streams",
    "api_latency_ms": "API Latency (ms)",
}

OPERATORS = [">", ">=", "<", "<="]
SEVERITIES = ["warning", "critical"]

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


@dataclass
class AlertRule:
    id: str
    name: str
    metric: str
    operator: str
    threshold: float
    severity: str = "warning"
    enabled: bool = True

    def as_dict(self) -> dict:
        return asdict(self)

    def evaluate(self, stats) -> bool:
        """Return True if this rule is currently triggered by *stats*."""
        if not self.enabled:
            return False
        value = getattr(stats, self.metric, None)
        if value is None:
            return False
        op = _OPS.get(self.operator)
        if op is None:
            return False
        try:
            return op(float(value), float(self.threshold))
        except (TypeError, ValueError):
            return False


def _load() -> list:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(rules: list) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(rules, f, indent=2)


def list_rules() -> list[AlertRule]:
    return [AlertRule(**r) for r in _load()]


def get_rule(rule_id: str) -> Optional[AlertRule]:
    for r in _load():
        if r["id"] == rule_id:
            return AlertRule(**r)
    return None


def create_rule(
    name: str,
    metric: str,
    operator: str,
    threshold: float,
    severity: str = "warning",
) -> AlertRule:
    if metric not in METRICS:
        raise ValueError(f"Unknown metric: {metric!r}")
    if operator not in OPERATORS:
        raise ValueError(f"Unknown operator: {operator!r}")
    if severity not in SEVERITIES:
        raise ValueError(f"Unknown severity: {severity!r}")

    rules = _load()
    rule = AlertRule(
        id=str(uuid.uuid4())[:8],
        name=name.strip(),
        metric=metric,
        operator=operator,
        threshold=float(threshold),
        severity=severity,
        enabled=True,
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


def evaluate_all(stats) -> list[tuple[AlertRule, bool]]:
    """Return (rule, triggered) pairs for every rule against current *stats*."""
    return [(rule, rule.evaluate(stats)) for rule in list_rules()]
