"""Webhook notification delivery for triggered alert rules.

Sends a single POST to a configured URL with a JSON payload listing all
currently-triggered rules. Uses a cooldown so repeated page loads don't
spam the endpoint.

Config is stored in a JSON file (path via NOTIFICATIONS_FILE env var).
Schema: {"webhook_url": "...", "cooldown_minutes": 10, "last_fired": "ISO"}
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import app.utils.http as http_util
from app.services import webhook_log


_STORE_PATH = os.environ.get("NOTIFICATIONS_FILE", "/tmp/notifications_config.json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> dict:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(cfg: dict) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get_config() -> dict:
    cfg = _load()
    return {
        "webhook_url": cfg.get("webhook_url", ""),
        "cooldown_minutes": int(cfg.get("cooldown_minutes", 10)),
        "last_fired": cfg.get("last_fired", ""),
    }


def save_config(webhook_url: str, cooldown_minutes: int = 10) -> None:
    cfg = _load()
    cfg["webhook_url"] = webhook_url.strip()
    cfg["cooldown_minutes"] = max(1, int(cooldown_minutes))
    _save(cfg)


def _cooldown_elapsed(cfg: dict) -> bool:
    """Return True if enough time has passed since the last webhook fire."""
    last_fired = cfg.get("last_fired", "")
    if not last_fired:
        return True
    try:
        last_dt = datetime.fromisoformat(last_fired)
        cooldown = timedelta(minutes=int(cfg.get("cooldown_minutes", 10)))
        return _now() - last_dt >= cooldown
    except (ValueError, TypeError):
        return True


def fire_webhook(triggered_rules: list, force: bool = False) -> Optional[dict]:
    """POST a notification if rules are triggered and cooldown has elapsed.

    Returns a result dict {"status": int|None, "error": str|None} or None
    when skipped (no URL, no triggered rules, or cooldown active).
    """
    if not triggered_rules:
        return None

    cfg = _load()
    url = cfg.get("webhook_url", "").strip()
    if not url:
        return None

    if not force and not _cooldown_elapsed(cfg):
        return None

    payload = json.dumps({
        "source": "livekit-dashboard",
        "fired_at": _now().isoformat(timespec="seconds"),
        "triggered_rules": [
            {
                "id": r.id,
                "name": r.name,
                "metric": r.metric,
                "operator": r.operator,
                "threshold": r.threshold,
                "severity": r.severity,
            }
            for r in triggered_rules
        ],
    }).encode()

    payload_str = payload.decode()
    post_result = http_util.post_json(url, payload_str)
    result = {"status": post_result.get("status"), "error": post_result.get("error")}

    webhook_log.log_delivery("alert", url, payload_str, result.get("status"), result.get("error"))

    cfg["last_fired"] = _now().isoformat(timespec="seconds")
    _save(cfg)
    return result
