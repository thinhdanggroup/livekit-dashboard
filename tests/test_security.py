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

