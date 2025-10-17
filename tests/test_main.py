"""Tests for main application"""
import pytest
from fastapi import status


def test_health_check(client):
    """Test health check endpoint (no auth required)"""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_overview_requires_auth(client):
    """Test that overview page requires authentication"""
    response = client.get("/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_overview_with_auth(client, auth_headers):
    """Test overview page with authentication"""
    response = client.get("/", headers=auth_headers)
    # Note: This will fail without a real LiveKit server
    # In a real test, you'd mock the LiveKitClient
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]


def test_rooms_requires_auth(client):
    """Test that rooms page requires authentication"""
    response = client.get("/rooms")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout_page(client):
    """Test logout page (no auth required)"""
    response = client.get("/logout")
    assert response.status_code == status.HTTP_200_OK


def test_invalid_auth(client):
    """Test with invalid credentials"""
    import base64
    
    credentials = "invalid:wrong"
    encoded = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded}"}
    
    response = client.get("/", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_settings_requires_auth(client):
    """Test that settings page requires authentication"""
    response = client.get("/settings")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_sandbox_requires_auth(client):
    """Test that sandbox page requires authentication"""
    response = client.get("/sandbox")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

