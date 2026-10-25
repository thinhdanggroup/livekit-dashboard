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

