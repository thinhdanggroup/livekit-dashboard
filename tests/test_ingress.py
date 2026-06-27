"""Tests for ingress management routes."""
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
    lk.list_ingress = AsyncMock(return_value=[])
    lk.create_ingress = AsyncMock(return_value=MagicMock(ingress_id="IN_test123"))
    lk.update_ingress = AsyncMock(return_value=MagicMock())
    lk.delete_ingress = AsyncMock(return_value=None)
    return lk


@pytest.fixture
def ingress_client():
    from app.main import app
    from app.services.livekit import get_livekit_client

    mock_lk = _make_mock_lk()
    app.dependency_overrides[get_livekit_client] = lambda: mock_lk

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_lk

    app.dependency_overrides.pop(get_livekit_client, None)


class TestIngressAuthGuards:
    def test_ingress_page_requires_auth(self, client):
        assert client.get("/ingress").status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_ingress_requires_auth(self, client):
        r = client.post("/ingress/create", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_ingress_requires_auth(self, client):
        r = client.post("/ingress/update", data={"csrf_token": "x", "ingress_id": "IN_x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_ingress_requires_auth(self, client):
        r = client.post("/ingress/delete", data={"csrf_token": "x", "ingress_id": "IN_x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED


class TestIngressPageLoad:
    def test_ingress_page_loads(self, ingress_client):
        c, _ = ingress_client
        r = c.get("/ingress", headers=_auth_headers())
        assert r.status_code == status.HTTP_200_OK
        assert b"Ingress" in r.content


class TestIngressCRUD:
    def test_create_ingress_rtmp(self, ingress_client):
        c, mock_lk = ingress_client
        token = _csrf_token()
        r = c.post(
            "/ingress/create",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "ingress_type": "rtmp",
                "name": "test-stream",
                "room_name": "my-room",
                "participant_identity": "streamer",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.create_ingress.assert_awaited_once()
        kw = mock_lk.create_ingress.call_args.kwargs
        assert kw["ingress_type"] == "rtmp"
        assert kw["name"] == "test-stream"
        assert kw["room_name"] == "my-room"

    def test_create_ingress_whip(self, ingress_client):
        c, mock_lk = ingress_client
        token = _csrf_token()
        r = c.post(
            "/ingress/create",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "ingress_type": "whip",
                "name": "whip-stream",
                "room_name": "my-room",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        kw = mock_lk.create_ingress.call_args.kwargs
        assert kw["ingress_type"] == "whip"

    def test_create_ingress_bad_csrf(self, ingress_client):
        c, mock_lk = ingress_client
        r = c.post(
            "/ingress/create",
            headers=_auth_headers(),
            data={"csrf_token": "bad", "ingress_type": "rtmp", "name": "x", "room_name": "r"},
            follow_redirects=False,
        )
        assert r.status_code in (
            status.HTTP_303_SEE_OTHER,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
        )
        mock_lk.create_ingress.assert_not_awaited()

    def test_update_ingress(self, ingress_client):
        c, mock_lk = ingress_client
        token = _csrf_token()
        r = c.post(
            "/ingress/update",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "ingress_id": "IN_abc123",
                "name": "updated-stream",
                "room_name": "new-room",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.update_ingress.assert_awaited_once()
        kw = mock_lk.update_ingress.call_args.kwargs
        assert kw["ingress_id"] == "IN_abc123"

    def test_delete_ingress(self, ingress_client):
        c, mock_lk = ingress_client
        token = _csrf_token()
        r = c.post(
            "/ingress/delete",
            headers=_auth_headers(),
            data={"csrf_token": token, "ingress_id": "IN_abc123"},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.delete_ingress.assert_awaited_once_with(ingress_id="IN_abc123")
