"""Tests for webhook notification service."""

import json
import pytest
from dataclasses import dataclass
from unittest.mock import patch, MagicMock


@dataclass
class _Rule:
    id: str = "r1"
    name: str = "Test rule"
    metric: str = "rooms_total"
    operator: str = ">"
    threshold: float = 0
    severity: str = "warning"


def test_get_config_defaults(tmp_path):
    import app.services.notifications as n
    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        cfg = n.get_config()
    assert cfg["webhook_url"] == ""
    assert cfg["cooldown_minutes"] == 10
    assert cfg["last_fired"] == ""


def test_save_and_get_config(tmp_path):
    import app.services.notifications as n
    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        n.save_config("https://example.com/hook", cooldown_minutes=5)
        cfg = n.get_config()
    assert cfg["webhook_url"] == "https://example.com/hook"
    assert cfg["cooldown_minutes"] == 5


def test_fire_webhook_no_triggered(tmp_path):
    import app.services.notifications as n
    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        result = n.fire_webhook([])
    assert result is None


def test_fire_webhook_no_url(tmp_path):
    import app.services.notifications as n
    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        result = n.fire_webhook([_Rule()])
    assert result is None


def test_fire_webhook_success(tmp_path):
    import app.services.notifications as n
    import urllib.request

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200

    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        n.save_config("https://example.com/hook")
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = n.fire_webhook([_Rule()])

    assert result is not None
    assert result["status"] == 200
    assert result["error"] is None


def test_fire_webhook_records_last_fired(tmp_path):
    import app.services.notifications as n
    import urllib.request

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200

    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        n.save_config("https://example.com/hook")
        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            n.fire_webhook([_Rule()])
        cfg = n.get_config()

    assert cfg["last_fired"] != ""


def test_fire_webhook_respects_cooldown(tmp_path):
    import app.services.notifications as n
    import urllib.request
    from datetime import datetime, timezone

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200

    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        n.save_config("https://example.com/hook", cooldown_minutes=60)
        # Pre-populate a recent last_fired
        cfg_data = {"webhook_url": "https://example.com/hook", "cooldown_minutes": 60,
                    "last_fired": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (tmp_path / "notif.json").write_text(json.dumps(cfg_data))

        with patch.object(urllib.request, "urlopen", return_value=mock_resp) as mock_open:
            result = n.fire_webhook([_Rule()])
            mock_open.assert_not_called()

    assert result is None


def test_fire_webhook_force_bypasses_cooldown(tmp_path):
    import app.services.notifications as n
    import urllib.request
    from datetime import datetime, timezone

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 204

    with patch.object(n, "_STORE_PATH", str(tmp_path / "notif.json")):
        cfg_data = {"webhook_url": "https://example.com/hook", "cooldown_minutes": 60,
                    "last_fired": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (tmp_path / "notif.json").write_text(json.dumps(cfg_data))

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = n.fire_webhook([_Rule()], force=True)

    assert result is not None
    assert result["status"] == 204
