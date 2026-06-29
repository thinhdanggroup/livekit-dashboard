"""Tests for Phase 9.4 — read-only role enforcement."""

import pytest
from unittest.mock import patch


def test_admin_mode_allows_post(client, auth_headers):
    """With DASHBOARD_ROLE=admin (default), POST should not be blocked by readonly middleware."""
    from app.security.csrf import generate_csrf_token
    token = generate_csrf_token()
    with patch.dict("os.environ", {"DASHBOARD_ROLE": "admin"}):
        resp = client.post(
            "/alerts",
            data={"csrf_token": token, "name": "test", "metric": "rooms_total",
                  "operator": ">", "threshold": "5", "severity": "warning"},
            headers=auth_headers,
        )
    # Not blocked by readonly middleware (other errors like LiveKit down are OK)
    assert b"Read-only" not in resp.content or resp.status_code != 403


def test_admin_mode_get_events_page(client, auth_headers):
    resp = client.get("/events", headers=auth_headers)
    assert resp.status_code == 200


def test_readonly_blocks_post(client, auth_headers):
    from app.security.csrf import generate_csrf_token
    token = generate_csrf_token()
    with patch.dict("os.environ", {"DASHBOARD_ROLE": "readonly"}):
        resp = client.post(
            "/alerts",
            data={"csrf_token": token, "name": "test", "metric": "rooms_total",
                  "operator": ">", "threshold": "5", "severity": "warning"},
            headers=auth_headers,
        )
    assert resp.status_code == 403
    assert b"Read-only" in resp.content


def test_readonly_blocks_post_rooms(client, auth_headers):
    from app.security.csrf import generate_csrf_token
    token = generate_csrf_token()
    with patch.dict("os.environ", {"DASHBOARD_ROLE": "readonly"}):
        resp = client.post(
            "/rooms",
            data={"csrf_token": token, "room_name": "x", "empty_timeout": "300",
                  "max_participants": "0", "metadata": ""},
            headers=auth_headers,
        )
    assert resp.status_code == 403


def test_readonly_allows_get(client, auth_headers):
    with patch.dict("os.environ", {"DASHBOARD_ROLE": "readonly"}):
        resp = client.get("/rooms", headers=auth_headers)
    # GET is allowed; may fail due to LiveKit connectivity but not readonly 403
    assert resp.status_code != 403 or b"Read-only" not in resp.content


def test_readonly_allows_logout_get(client):
    """Logout GET must work even in readonly mode."""
    with patch.dict("os.environ", {"DASHBOARD_ROLE": "readonly"}):
        resp = client.get("/logout")
    assert resp.status_code in (200, 302, 303)


def test_readonly_template_global_true():
    """is_readonly() template global returns True when DASHBOARD_ROLE=readonly."""
    with patch.dict("os.environ", {"DASHBOARD_ROLE": "readonly"}):
        import app.main as m
        result = m.templates.env.globals["is_readonly"]()
    assert result is True


def test_readonly_template_global_false():
    with patch.dict("os.environ", {"DASHBOARD_ROLE": "admin"}):
        import app.main as m
        result = m.templates.env.globals["is_readonly"]()
    assert result is False


def test_default_is_not_readonly():
    """Without DASHBOARD_ROLE, is_readonly() defaults to False."""
    env_without_role = {k: v for k, v in __import__("os").environ.items()
                        if k != "DASHBOARD_ROLE"}
    with patch.dict("os.environ", env_without_role, clear=True):
        import app.main as m
        result = m.templates.env.globals["is_readonly"]()
    assert result is False
