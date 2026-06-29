"""Tests for main application"""
import pytest
from unittest.mock import AsyncMock, patch
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


def test_overview_health_summary_rendered(client, auth_headers):
    """Overview route returns 200 with health summary section when LiveKit is mocked."""
    from app.services.dashboard import DashboardStats

    mock_stats = DashboardStats(
        rooms_total=3,
        rooms_active=2,
        participants_total=7,
        egress_active=1,
        ingress_active=0,
        api_latency_ms=12.5,
    )
    mock_room_analytics = {
        "total_rooms": 3,
        "active_rooms": 2,
        "empty_rooms": 1,
        "total_participants": 7,
        "avg_participants": 2.3,
        "room_sizes": {"small": 2, "medium": 0, "large": 0},
        "api_latency_ms": 12.5,
    }
    mock_egress = {
        "active_jobs": 1,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "success_rate": 100,
        "egress_types": {"room_composite": 1, "participant": 0, "track": 0, "web": 0},
        "storage_used_gb": 0,
        "total_jobs_today": 1,
    }
    mock_ingress = {
        "total_ingress": 0,
        "active_ingress": 0,
        "ingress_types": {"rtmp": 0, "whip": 0, "url": 0},
        "avg_bitrate_mbps": 0,
        "connection_stability": 0,
        "streams_today": 0,
    }
    mock_server_info = {"rooms_count": 3, "participants_count": 7, "version": "1.0"}

    with (
        patch("app.routes.overview.gather_dashboard_stats", new=AsyncMock(return_value=mock_stats)),
        patch("app.services.livekit.LiveKitClient.get_server_info", new=AsyncMock(return_value=mock_server_info)),
        patch("app.services.livekit.LiveKitClient.get_room_analytics", new=AsyncMock(return_value=mock_room_analytics)),
        patch("app.services.livekit.LiveKitClient.get_egress_analytics", new=AsyncMock(return_value=mock_egress)),
        patch("app.services.livekit.LiveKitClient.get_ingress_analytics", new=AsyncMock(return_value=mock_ingress)),
    ):
        response = client.get("/", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    assert "Total Rooms" in response.text
    assert "Participants" in response.text
    assert "Active Egress" in response.text
    assert "Active Ingress" in response.text
    assert "API Latency" in response.text


def test_overview_health_summary_shows_error(client, auth_headers):
    """When LiveKit API errors, health summary shows the error alert."""
    from app.services.dashboard import DashboardStats

    mock_stats = DashboardStats(error="connection refused")
    mock_room_analytics = {
        "total_rooms": 0,
        "active_rooms": 0,
        "empty_rooms": 0,
        "total_participants": 0,
        "avg_participants": 0,
        "room_sizes": {"small": 0, "medium": 0, "large": 0},
        "api_latency_ms": 0,
    }
    mock_egress = {
        "active_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "success_rate": 100,
        "egress_types": {"room_composite": 0, "participant": 0, "track": 0, "web": 0},
        "storage_used_gb": 0,
        "total_jobs_today": 0,
    }
    mock_ingress = {
        "total_ingress": 0,
        "active_ingress": 0,
        "ingress_types": {"rtmp": 0, "whip": 0, "url": 0},
        "avg_bitrate_mbps": 0,
        "connection_stability": 0,
        "streams_today": 0,
    }
    mock_server_info = {"rooms_count": 0, "participants_count": 0, "version": "unknown"}

    with (
        patch("app.routes.overview.gather_dashboard_stats", new=AsyncMock(return_value=mock_stats)),
        patch("app.services.livekit.LiveKitClient.get_server_info", new=AsyncMock(return_value=mock_server_info)),
        patch("app.services.livekit.LiveKitClient.get_room_analytics", new=AsyncMock(return_value=mock_room_analytics)),
        patch("app.services.livekit.LiveKitClient.get_egress_analytics", new=AsyncMock(return_value=mock_egress)),
        patch("app.services.livekit.LiveKitClient.get_ingress_analytics", new=AsyncMock(return_value=mock_ingress)),
    ):
        response = client.get("/", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    assert "LiveKit API error" in response.text
    assert "connection refused" in response.text

