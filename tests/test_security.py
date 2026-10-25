"""Tests for security modules"""
import os
import pytest
from app.security.basic_auth import verify_credentials
from app.security.csrf import generate_csrf_token, validate_csrf_token
from fastapi.security import HTTPBasicCredentials


def test_verify_credentials_valid():
    """Test valid credentials"""
    creds = HTTPBasicCredentials(
        username=os.environ["ADMIN_USERNAME"],
        password=os.environ["ADMIN_PASSWORD"]
    )
    assert verify_credentials(creds) is True


def test_verify_credentials_invalid():
    """Test invalid credentials"""
    creds = HTTPBasicCredentials(username="wrong", password="wrong")
    assert verify_credentials(creds) is False


def test_csrf_token_generation():
    """Test CSRF token generation"""
    token = generate_csrf_token()
    assert token is not None
    assert len(token) > 0
    assert isinstance(token, str)


def test_csrf_token_validation():
    """Test CSRF token validation"""
    token = generate_csrf_token()
    assert validate_csrf_token(token) is True


def test_csrf_token_invalid():
    """Test invalid CSRF token"""
    assert validate_csrf_token("invalid-token") is False
    assert validate_csrf_token("") is False


def test_csrf_token_uniqueness():
    """Test that each generated token is unique"""
    token1 = generate_csrf_token()
    token2 = generate_csrf_token()
    assert token1 != token2


def test_requires_admin_logs_failed_attempt(client, tmp_path, monkeypatch):
    """A failed login attempt via requires_admin is recorded in the security log."""
    import app.services.security_log as sl
    monkeypatch.setattr(sl, "_STORE_PATH", str(tmp_path / "s.json"))
    import base64
    bad = base64.b64encode(b"wrong:wrong").decode()
    client.get("/rooms", headers={"Authorization": f"Basic {bad}"})
    entries = sl.list_failed_logins()
    assert len(entries) == 1
    assert entries[0]["username"] == "wrong"


def test_requires_admin_does_not_log_success(client, auth_headers, tmp_path, monkeypatch):
    """A successful login via requires_admin does NOT get logged."""
    import app.services.security_log as sl
    monkeypatch.setattr(sl, "_STORE_PATH", str(tmp_path / "s.json"))
    client.get("/rooms", headers=auth_headers)
    assert sl.list_failed_logins() == []


def _csrf():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


def test_blocked_ip_gets_403(client, tmp_path, monkeypatch):
    """A client whose IP is not on a configured allowlist gets 403, except on /health.

    Also verifies no basic-auth challenge leaks: the 403 must come from the
    IP-allowlist middleware short-circuiting BEFORE requires_admin ever
    runs, so there must be no WWW-Authenticate header on the response.
    """
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    ipa.save_allowlist("203.0.113.5", requester_ip="203.0.113.5")  # testclient's IP is not this
    resp = client.get("/health")  # exempt path still works
    assert resp.status_code == 200
    resp2 = client.get("/rooms")
    assert resp2.status_code == 403
    assert "WWW-Authenticate" not in resp2.headers
    assert resp2.content == b"Access denied."


def test_blocked_ip_post_gets_generic_denial_not_readonly_message(client, tmp_path, monkeypatch):
    """A blocked IP's mutating POST must get the flat IP-allowlist denial,
    never the readonly-mode message or a CORS-specific response -- the IP
    check must run before both of those middlewares, not after."""
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    ipa.save_allowlist("203.0.113.5", requester_ip="203.0.113.5")
    monkeypatch.setenv("DASHBOARD_ROLE", "readonly")
    resp = client.post(
        "/rooms",
        data={"csrf_token": _csrf(), "room_name": "x", "empty_timeout": "300",
              "max_participants": "0", "metadata": ""},
    )
    assert resp.status_code == 403
    assert resp.content == b"Access denied."
    assert b"Read-only" not in resp.content


def test_corrupt_ip_allowlist_store_fails_open_through_middleware(client, auth_headers, tmp_path, monkeypatch):
    """A corrupted store (here: a directory sitting at the configured path,
    the realistic Docker-bind-mount failure mode) must never turn into a
    500 or a blanket 403 -- the middleware must fail open and let allowed
    requests through normally."""
    import app.services.ip_allowlist as ipa
    store_path = tmp_path / "a.json"
    store_path.mkdir()
    monkeypatch.setattr(ipa, "_STORE_PATH", str(store_path))
    resp = client.get("/rooms", headers=auth_headers)
    assert resp.status_code == 200


def test_allowlisted_ip_passes(client, tmp_path, monkeypatch, auth_headers):
    """A client whose IP IS on the configured allowlist passes through normally."""
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    # TestClient's default client host is "testclient" — allowlist it explicitly
    ipa.save_allowlist("testclient", requester_ip="testclient")
    resp = client.get("/rooms", headers=auth_headers)
    assert resp.status_code == 200


def test_settings_page_shows_failed_logins_and_allowlist_form(client, auth_headers, tmp_path, monkeypatch):
    """The settings page surfaces recent failed logins AND the allowlist
    management form (pre-filled from the current allowlist)."""
    import app.services.security_log as sl
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(sl, "_STORE_PATH", str(tmp_path / "s.json"))
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    sl.log_failed_login("9.9.9.9", "admin")
    ipa.save_allowlist("198.51.100.9, testclient", requester_ip="testclient")
    resp = client.get("/settings", headers=auth_headers)
    assert resp.status_code == 200
    assert b"9.9.9.9" in resp.content
    assert b'name="ip_allowlist"' in resp.content
    assert b'action="/settings/security"' in resp.content
    assert b"198.51.100.9" in resp.content  # pre-filled from ip_allowlist_raw


def test_security_form_hidden_in_readonly_mode(client, auth_headers, monkeypatch):
    """The allowlist-save form must be gated by is_readonly(), matching the
    pattern used for other mutating controls (e.g. the rooms delete button)."""
    monkeypatch.setenv("DASHBOARD_ROLE", "readonly")
    resp = client.get("/settings", headers=auth_headers)
    assert resp.status_code == 200
    assert b'action="/settings/security"' not in resp.content


def test_save_security_settings_updates_allowlist(client, auth_headers, tmp_path, monkeypatch):
    """POST /settings/security persists the submitted allowlist, redirects,
    and -- critically -- always keeps the requester's own IP in the saved
    list so the submitting operator can never lock themselves out."""
    import app.services.ip_allowlist as ipa
    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "a.json"))
    resp = client.post("/settings/security", headers=auth_headers,
                        data={"csrf_token": _csrf(), "ip_allowlist": "203.0.113.5"},
                        follow_redirects=False)
    assert resp.status_code == 303
    saved = ipa.get_allowlist()
    assert "203.0.113.5" in saved
    # TestClient's request.client.host is the literal string "testclient" --
    # that's the requester_ip save_security_settings must have passed through.
    assert "testclient" in saved

