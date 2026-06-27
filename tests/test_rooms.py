"""Tests for room update and participant management routes."""
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
    lk.list_rooms = AsyncMock(return_value=([], 0.0))
    lk.get_room = AsyncMock(return_value=MagicMock(name="test-room", metadata=""))
    lk.create_room = AsyncMock(return_value=MagicMock())
    lk.delete_room = AsyncMock(return_value=None)
    lk.update_room_metadata = AsyncMock(return_value=MagicMock())
    lk.list_participants = AsyncMock(return_value=[])
    lk.remove_participant = AsyncMock(return_value=None)
    lk.mute_participant_track = AsyncMock(return_value=MagicMock())
    lk.update_participant = AsyncMock(return_value=MagicMock())
    return lk


@pytest.fixture
def rooms_client():
    from app.main import app
    from app.services.livekit import get_livekit_client

    mock_lk = _make_mock_lk()
    app.dependency_overrides[get_livekit_client] = lambda: mock_lk

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_lk

    app.dependency_overrides.pop(get_livekit_client, None)


class TestRoomAuthGuards:
    def test_room_update_requires_auth(self, client):
        r = client.post("/rooms/test-room/update", data={"csrf_token": "x", "metadata": ""})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_participant_update_requires_auth(self, client):
        r = client.post("/rooms/r/participants/p/update", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_participant_mute_requires_auth(self, client):
        r = client.post("/rooms/r/participants/p/mute", data={"csrf_token": "x", "track_sid": "t", "muted": "true"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED


class TestRoomUpdate:
    def test_update_room_metadata(self, rooms_client):
        c, mock_lk = rooms_client
        token = _csrf_token()
        r = c.post(
            "/rooms/test-room/update",
            headers=_auth_headers(),
            data={"csrf_token": token, "metadata": '{"env":"prod"}'},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.update_room_metadata.assert_awaited_once_with("test-room", '{"env":"prod"}')


class TestParticipantManagement:
    def test_mute_participant(self, rooms_client):
        c, mock_lk = rooms_client
        token = _csrf_token()
        r = c.post(
            "/rooms/my-room/participants/alice/mute",
            headers=_auth_headers(),
            data={"csrf_token": token, "track_sid": "TR_abc", "muted": "true"},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.mute_participant_track.assert_awaited_once_with("my-room", "alice", "TR_abc", True)

    def test_unmute_participant(self, rooms_client):
        c, mock_lk = rooms_client
        token = _csrf_token()
        r = c.post(
            "/rooms/my-room/participants/alice/mute",
            headers=_auth_headers(),
            data={"csrf_token": token, "track_sid": "TR_abc", "muted": "false"},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.mute_participant_track.assert_awaited_once_with("my-room", "alice", "TR_abc", False)

    def test_update_participant_metadata(self, rooms_client):
        c, mock_lk = rooms_client
        token = _csrf_token()
        r = c.post(
            "/rooms/my-room/participants/alice/update",
            headers=_auth_headers(),
            data={"csrf_token": token, "metadata": '{"role":"host"}'},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        mock_lk.update_participant.assert_awaited_once()
        kw = mock_lk.update_participant.call_args.kwargs
        assert kw["metadata"] == '{"role":"host"}'

    def test_update_participant_bad_csrf(self, rooms_client):
        c, mock_lk = rooms_client
        r = c.post(
            "/rooms/my-room/participants/alice/update",
            headers=_auth_headers(),
            data={"csrf_token": "invalid", "metadata": "x"},
            follow_redirects=False,
        )
        assert r.status_code in (
            status.HTTP_303_SEE_OTHER,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
        )
        mock_lk.update_participant.assert_not_awaited()
