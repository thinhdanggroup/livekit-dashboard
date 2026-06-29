"""Tests for audit log service and routes."""

import pytest
from unittest.mock import patch


def _csrf():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

def test_list_entries_empty(tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        assert al.list_entries() == []


def test_log_action_persists(tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        al.log_action("room.create", "my-room", user="admin", details={"max_participants": 10})
        entries = al.list_entries()
    assert len(entries) == 1
    assert entries[0]["action"] == "room.create"
    assert entries[0]["target"] == "my-room"
    assert entries[0]["user"] == "admin"
    assert entries[0]["details"]["max_participants"] == 10


def test_list_entries_newest_first(tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        al.log_action("room.create", "first")
        al.log_action("room.delete", "second")
        entries = al.list_entries()
    assert entries[0]["action"] == "room.delete"
    assert entries[1]["action"] == "room.create"


def test_clear_removes_all(tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        al.log_action("room.create", "r")
        al.clear()
        assert al.list_entries() == []


def test_log_action_never_raises(tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", "/nonexistent/path/audit.json"):
        al.log_action("room.create", "r")  # must not raise


def test_list_entries_limit(tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        for i in range(10):
            al.log_action("room.create", f"room-{i}")
        entries = al.list_entries(limit=3)
    assert len(entries) == 3


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_audit_page_requires_auth(client):
    resp = client.get("/audit", follow_redirects=False)
    assert resp.status_code == 401


def test_audit_page_returns_200(client, auth_headers, tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        resp = client.get("/audit", headers=auth_headers)
    assert resp.status_code == 200
    assert b"Audit Log" in resp.content


def test_audit_page_shows_entries(client, auth_headers, tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        al.log_action("room.create", "test-room", user="admin")
        resp = client.get("/audit", headers=auth_headers)
    assert b"room.create" in resp.content
    assert b"test-room" in resp.content


def test_clear_audit_log_via_route(client, auth_headers, tmp_path):
    import app.services.audit_log as al
    with patch.object(al, "_STORE_PATH", str(tmp_path / "audit.json")):
        al.log_action("room.create", "r")
        resp = client.post(
            "/audit/clear",
            data={"csrf_token": _csrf()},
            headers=auth_headers,
            follow_redirects=False,
        )
    assert resp.status_code == 303
