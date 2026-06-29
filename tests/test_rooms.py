"""Tests for room update and participant management routes."""
import json
import os
import tempfile
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


class TestRoomsExportCsv:
    def _make_room(self, name, participants=2, max_p=100, timeout=300, metadata=""):
        r = MagicMock()
        r.name = name
        r.num_participants = participants
        r.max_participants = max_p
        r.creation_time = 0
        r.empty_timeout = timeout
        r.metadata = metadata
        return r

    def test_export_requires_auth(self, client):
        r = client.get("/rooms/export.csv")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_export_returns_csv(self, rooms_client):
        c, mock_lk = rooms_client
        mock_lk.list_rooms = AsyncMock(return_value=([
            self._make_room("room-a", participants=3, metadata='{"env":"prod"}'),
            self._make_room("room-b"),
        ], 0.0))
        r = c.get("/rooms/export.csv", headers=_auth_headers())
        assert r.status_code == status.HTTP_200_OK
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        lines = r.text.strip().splitlines()
        assert lines[0] == "name,num_participants,max_participants,creation_time,empty_timeout,metadata"
        assert len(lines) == 3  # header + 2 rooms

    def test_export_filters_by_search(self, rooms_client):
        c, mock_lk = rooms_client
        mock_lk.list_rooms = AsyncMock(return_value=([
            self._make_room("prod-room"),
            self._make_room("dev-room"),
        ], 0.0))
        r = c.get("/rooms/export.csv?search=prod", headers=_auth_headers())
        assert r.status_code == status.HTTP_200_OK
        lines = r.text.strip().splitlines()
        assert len(lines) == 2  # header + 1 matching room
        assert "prod-room" in lines[1]

    def test_export_empty_when_no_rooms(self, rooms_client):
        c, mock_lk = rooms_client
        mock_lk.list_rooms = AsyncMock(return_value=([], 0.0))
        r = c.get("/rooms/export.csv", headers=_auth_headers())
        assert r.status_code == status.HTTP_200_OK
        lines = r.text.strip().splitlines()
        assert len(lines) == 1  # header only


class TestRoomsPartialRefresh:
    def test_partial_returns_table_fragment(self, rooms_client):
        c, mock_lk = rooms_client
        r = c.get("/rooms?partial=1", headers=_auth_headers())
        assert r.status_code == status.HTTP_200_OK
        # Partial returns the table div, not the full page
        assert 'id="rooms-list"' in r.text
        assert "<html" not in r.text


class TestPinRoom:
    def test_pin_requires_auth(self, client):
        r = client.post("/rooms/test-room/pin", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unpin_requires_auth(self, client):
        r = client.post("/rooms/test-room/unpin", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_pin_room_redirects(self, rooms_client, tmp_path, monkeypatch):
        import app.services.room_annotations as ann
        store = tmp_path / "annotations.json"
        monkeypatch.setattr(ann, "_STORE_PATH", str(store))

        c, _ = rooms_client
        token = _csrf_token()
        r = c.post(
            "/rooms/my-room/pin",
            headers=_auth_headers(),
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "my-room" in ann.get_pinned()

    def test_unpin_room_redirects(self, rooms_client, tmp_path, monkeypatch):
        import app.services.room_annotations as ann
        store = tmp_path / "annotations.json"
        monkeypatch.setattr(ann, "_STORE_PATH", str(store))
        ann.pin_room("my-room")  # pre-pin

        c, _ = rooms_client
        token = _csrf_token()
        r = c.post(
            "/rooms/my-room/unpin",
            headers=_auth_headers(),
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "my-room" not in ann.get_pinned()

    def test_pin_idempotent(self, tmp_path, monkeypatch):
        import app.services.room_annotations as ann
        store = tmp_path / "annotations.json"
        monkeypatch.setattr(ann, "_STORE_PATH", str(store))
        ann.pin_room("room-a")
        ann.pin_room("room-a")
        assert ann.get_pinned().count("room-a") == 1


class TestAnnotateRoom:
    def test_annotate_requires_auth(self, client):
        r = client.post("/rooms/test-room/annotate", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_annotate_saves_note_and_tags(self, rooms_client, tmp_path, monkeypatch):
        import app.services.room_annotations as ann
        store = tmp_path / "annotations.json"
        monkeypatch.setattr(ann, "_STORE_PATH", str(store))

        c, mock_lk = rooms_client
        mock_room = MagicMock()
        mock_room.name = "prod-room"
        mock_room.num_participants = 2
        mock_room.max_participants = 100
        mock_room.creation_time = 0
        mock_room.empty_timeout = 300
        mock_room.metadata = ""
        mock_lk.list_rooms = AsyncMock(return_value=([mock_room], 0.0))
        mock_lk.list_participants = AsyncMock(return_value=[])

        token = _csrf_token()
        r = c.post(
            "/rooms/prod-room/annotate",
            headers=_auth_headers(),
            data={"csrf_token": token, "note": "Production room", "tags": ["prod", "VIP"]},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        saved = ann.get_annotations("prod-room")
        assert saved["note"] == "Production room"
        assert "prod" in saved["tags"]
        assert "VIP" in saved["tags"]

    def test_annotate_bad_csrf(self, rooms_client, tmp_path, monkeypatch):
        import app.services.room_annotations as ann
        store = tmp_path / "annotations.json"
        monkeypatch.setattr(ann, "_STORE_PATH", str(store))

        c, _ = rooms_client
        r = c.post(
            "/rooms/prod-room/annotate",
            headers=_auth_headers(),
            data={"csrf_token": "bad", "note": "should not save"},
            follow_redirects=False,
        )
        assert r.status_code in (
            status.HTTP_303_SEE_OTHER,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
        )
        saved = ann.get_annotations("prod-room")
        assert saved["note"] == ""


class TestRoomAnnotationsService:
    def test_pin_unpin_get_pinned(self, tmp_path, monkeypatch):
        import app.services.room_annotations as ann
        monkeypatch.setattr(ann, "_STORE_PATH", str(tmp_path / "ann.json"))
        assert ann.get_pinned() == []
        ann.pin_room("r1")
        ann.pin_room("r2")
        assert set(ann.get_pinned()) == {"r1", "r2"}
        ann.unpin_room("r1")
        assert ann.get_pinned() == ["r2"]

    def test_set_get_annotations(self, tmp_path, monkeypatch):
        import app.services.room_annotations as ann
        monkeypatch.setattr(ann, "_STORE_PATH", str(tmp_path / "ann.json"))
        ann.set_annotations("r1", "my note", ["prod", "demo"])
        result = ann.get_annotations("r1")
        assert result["note"] == "my note"
        assert result["tags"] == ["prod", "demo"]
        assert result["pinned"] is False

    def test_build_timeline_empty(self):
        from app.services.room_annotations import build_timeline
        room = MagicMock()
        room.creation_time = 1234567890
        events = build_timeline(room, [])
        assert len(events) == 1
        assert events[0]["kind"] == "room_created"

    def test_build_timeline_with_participants(self):
        from app.services.room_annotations import build_timeline
        room = MagicMock()
        room.creation_time = 1000

        p = MagicMock()
        p.identity = "alice"
        p.name = "Alice"
        p.joined_at = 2000
        track = MagicMock()
        track.type = 0  # audio
        track.sid = "TR_1"
        track.muted = False
        p.tracks = [track]

        events = build_timeline(room, [p])
        kinds = [e["kind"] for e in events]
        assert "room_created" in kinds
        assert "participant_joined" in kinds
        assert "track_published" in kinds
