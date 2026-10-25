"""Tests for diagnostics route — support bundle and webhook tester."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch


def _csrf():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


def _make_lk():
    lk = MagicMock()
    lk.sip_enabled = False
    lk.list_rooms = AsyncMock(return_value=([], 0.01))
    lk.list_participants = AsyncMock(return_value=[])
    return lk


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_diagnostics_page_requires_auth(client):
    resp = client.get("/diagnostics", follow_redirects=False)
    assert resp.status_code == 401


def test_diagnostics_page_returns_200(client, auth_headers):
    resp = client.get("/diagnostics", headers=auth_headers)
    assert resp.status_code == 200
    assert b"Diagnostics" in resp.content


def test_support_bundle_requires_auth(client):
    resp = client.get("/diagnostics/rooms/my-room/bundle.json", follow_redirects=False)
    assert resp.status_code == 401


def test_support_bundle_returns_json(client, auth_headers):
    from app.main import app
    from app.services.livekit import get_livekit_client

    mock_lk = _make_lk()
    app.dependency_overrides[get_livekit_client] = lambda: mock_lk
    try:
        resp = client.get("/diagnostics/rooms/test-room/bundle.json", headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_livekit_client, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["room_name"] == "test-room"
    assert "participants" in data
    assert "annotations" in data


def test_webhook_test_requires_auth(client):
    resp = client.post(
        "/diagnostics/webhook-test",
        data={"csrf_token": "x", "url": "http://example.com", "payload": "{}"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


def test_webhook_test_connection_error(client, auth_headers):
    """When the target URL is unreachable, the result shows an error message."""
    resp = client.post(
        "/diagnostics/webhook-test",
        data={
            "csrf_token": _csrf(),
            "url": "http://127.0.0.1:19999/no-such-endpoint",
            "payload": '{"event": "test"}',
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert b"Error" in resp.content or b"error" in resp.content


# ---------------------------------------------------------------------------
# Webhook delivery log view, manual-test logging, and replay route
# ---------------------------------------------------------------------------

def test_diagnostics_page_includes_log_table(client, auth_headers):
    resp = client.get("/diagnostics", headers=auth_headers)
    assert b"Webhook Delivery Log" in resp.content


def test_webhook_test_creates_log_entry(client, auth_headers, monkeypatch):
    import app.services.webhook_log as wl

    with patch("app.utils.http.post_json", return_value={"status": 200, "body": "ok", "error": None}):
        client.post(
            "/diagnostics/webhook-test",
            headers=auth_headers,
            data={"csrf_token": _csrf(), "url": "http://example.com", "payload": "{}"},
        )
    resp = client.get("/diagnostics", headers=auth_headers)
    assert b"manual_test" in resp.content or b"example.com" in resp.content


def test_webhook_replay_requires_auth(client):
    resp = client.post(
        "/diagnostics/webhook-log/abc123/replay",
        data={"csrf_token": "x"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


def test_webhook_replay_unknown_id_redirects(client, auth_headers):
    resp = client.post(
        "/diagnostics/webhook-log/doesnotexist/replay",
        headers=auth_headers,
        data={"csrf_token": _csrf()},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def test_webhook_replay_sends_and_logs(client, auth_headers, monkeypatch):
    import app.services.webhook_log as wl

    with patch.object(wl, "_STORE_PATH", "/tmp/test_webhook_replay_log.json"):
        if os.path.exists(wl._STORE_PATH):
            os.remove(wl._STORE_PATH)
        entry_id = wl.log_delivery("manual_test", "http://example.com/seed", "{}", 200, None)

        with patch("app.utils.http.post_json", return_value={"status": 204, "body": "", "error": None}):
            resp = client.post(
                f"/diagnostics/webhook-log/{entry_id}/replay",
                headers=auth_headers,
                data={"csrf_token": _csrf()},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        entries = wl.list_entries()
        replay_entries = [e for e in entries if e["source"] == "replay"]
        assert len(replay_entries) == 1
        assert replay_entries[0]["url"] == "http://example.com/seed"
        assert replay_entries[0]["status"] == 204

        os.remove(wl._STORE_PATH)
