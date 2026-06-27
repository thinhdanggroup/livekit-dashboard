"""Tests for additional egress types (track and web)."""
import os
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import status
from fastapi.testclient import TestClient


def _auth_headers():
    import base64
    creds = f"{os.environ['ADMIN_USERNAME']}:{os.environ['ADMIN_PASSWORD']}"
    return {"Authorization": f"Basic {base64.b64encode(creds.encode()).decode()}"}


def _csrf_token():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


def _make_mock_lk():
    lk = MagicMock()
    lk.sip_enabled = False
    lk.list_egress = AsyncMock(return_value=[])
    lk.start_room_composite_egress = AsyncMock(return_value=MagicMock())
    lk.start_track_egress = AsyncMock(return_value=MagicMock())
    lk.start_web_egress = AsyncMock(return_value=MagicMock())
    lk.stop_egress = AsyncMock(return_value=None)
    return lk


@pytest.fixture
def egress_client():
    from app.main import app
    from app.services.livekit import get_livekit_client

    mock_lk = _make_mock_lk()
    app.dependency_overrides[get_livekit_client] = lambda: mock_lk

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_lk

    app.dependency_overrides.pop(get_livekit_client, None)


class TestEgressAuthGuards:
    def test_track_egress_requires_auth(self, client):
        r = client.post("/egress/start/track", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_web_egress_requires_auth(self, client):
        r = client.post("/egress/start/web", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED


class TestEgressTypes:
    def test_start_room_composite_egress(self, egress_client):
        c, mock_lk = egress_client
        token = _csrf_token()
        r = c.post(
            "/egress/start",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "room_name": "my-room",
                "output_filename": "recording-{room}-{time}.mp4",
                "layout": "grid",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.start_room_composite_egress.assert_awaited_once()

    def test_start_track_egress(self, egress_client):
        c, mock_lk = egress_client
        token = _csrf_token()
        r = c.post(
            "/egress/start/track",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "room_name": "my-room",
                "track_sid": "TR_abc123",
                "output_filename": "track-{time}.mp4",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.start_track_egress.assert_awaited_once()
        kw = mock_lk.start_track_egress.call_args.kwargs
        assert kw["room_name"] == "my-room"
        assert kw["track_sid"] == "TR_abc123"

    def test_start_web_egress(self, egress_client):
        c, mock_lk = egress_client
        token = _csrf_token()
        r = c.post(
            "/egress/start/web",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "url": "https://example.com/room",
                "output_filename": "web-{time}.mp4",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.start_web_egress.assert_awaited_once()
        kw = mock_lk.start_web_egress.call_args.kwargs
        assert kw["url"] == "https://example.com/room"

    def test_stop_egress(self, egress_client):
        c, mock_lk = egress_client
        token = _csrf_token()
        r = c.post(
            "/egress/EG_abc123/stop",
            headers=_auth_headers(),
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.stop_egress.assert_awaited_once_with("EG_abc123")
