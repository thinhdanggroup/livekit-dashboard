"""Tests for app.services.search"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.search import SearchResult, search_all


def _make_lk(**overrides):
    lk = MagicMock()
    lk.sip_enabled = False
    lk.list_rooms = AsyncMock(return_value=([], 0.01))
    lk.get_all_participants_across_rooms = AsyncMock(return_value=[])
    lk.list_egress = AsyncMock(return_value=[])
    lk.list_ingress = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(lk, k, v)
    return lk


async def test_search_empty_q_returns_no_results_and_no_api_calls():
    lk = _make_lk()
    results = await search_all(lk, "")
    assert results == []
    lk.list_rooms.assert_not_called()
    lk.get_all_participants_across_rooms.assert_not_called()


async def test_search_rooms_by_name():
    room = MagicMock()
    room.name = "my-room"
    room.metadata = ""
    room.num_participants = 2
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "my-room")
    assert any(r.kind == "room" and r.title == "my-room" for r in results)


async def test_search_rooms_by_metadata():
    room = MagicMock()
    room.name = "conference"
    room.metadata = "project-alpha"
    room.num_participants = 0
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "alpha")
    assert any(r.kind == "room" for r in results)


async def test_search_rooms_no_match():
    room = MagicMock()
    room.name = "unrelated"
    room.metadata = ""
    room.num_participants = 0
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "xyz-never-match")
    assert not any(r.kind == "room" for r in results)


async def test_search_case_insensitive():
    room = MagicMock()
    room.name = "MainRoom"
    room.metadata = ""
    room.num_participants = 1
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "mainroom")
    assert any(r.kind == "room" for r in results)


async def test_search_participants_by_identity():
    p = MagicMock()
    p.identity = "user-alice"
    p.name = ""
    p.metadata = ""
    p._room_name = "room-1"
    lk = _make_lk(
        get_all_participants_across_rooms=AsyncMock(return_value=[p])
    )
    results = await search_all(lk, "alice")
    assert any(r.kind == "participant" and "user-alice" in r.title for r in results)


async def test_search_participants_by_room_name():
    p = MagicMock()
    p.identity = "bob"
    p.name = ""
    p.metadata = ""
    p._room_name = "special-room"
    lk = _make_lk(
        get_all_participants_across_rooms=AsyncMock(return_value=[p])
    )
    results = await search_all(lk, "special")
    assert any(r.kind == "participant" for r in results)


async def test_search_egress_by_room_name():
    job = MagicMock()
    job.egress_id = "eg-001"
    job.room_name = "broadcast-room"
    job.status = 1
    lk = _make_lk(list_egress=AsyncMock(return_value=[job]))
    results = await search_all(lk, "broadcast")
    assert any(r.kind == "egress" for r in results)


async def test_search_ingress_by_name():
    stream = MagicMock()
    stream.ingress_id = "in-001"
    stream.name = "camera-feed"
    stream.room_name = "live-room"
    stream.url = "rtmp://host/live"
    stream.status = MagicMock()
    lk = _make_lk(list_ingress=AsyncMock(return_value=[stream]))
    results = await search_all(lk, "camera")
    assert any(r.kind == "ingress" for r in results)


async def test_search_result_url_for_room():
    room = MagicMock()
    room.name = "target"
    room.metadata = ""
    room.num_participants = 0
    lk = _make_lk(list_rooms=AsyncMock(return_value=([room], 0.01)))
    results = await search_all(lk, "target")
    room_results = [r for r in results if r.kind == "room"]
    assert room_results[0].url == "/rooms/target"


async def test_search_api_error_returns_partial_results():
    """Errors on one entity type don't cancel others."""
    room = MagicMock()
    room.name = "healthy-room"
    room.metadata = ""
    room.num_participants = 1
    lk = _make_lk(
        list_rooms=AsyncMock(return_value=([room], 0.01)),
        get_all_participants_across_rooms=AsyncMock(side_effect=Exception("timeout")),
        list_egress=AsyncMock(side_effect=Exception("service down")),
    )
    results = await search_all(lk, "healthy")
    assert any(r.kind == "room" for r in results)
    assert not any(r.kind == "participant" for r in results)


async def test_search_result_is_dataclass():
    r = SearchResult(kind="room", title="t", subtitle="s", url="/rooms/t", status="active")
    assert r.kind == "room"
    assert r.title == "t"
    assert r.url == "/rooms/t"


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------

def test_search_route_empty_q_returns_200(client, auth_headers):
    resp = client.get("/search?q=", headers=auth_headers)
    assert resp.status_code == 200


def test_search_route_requires_auth(client):
    resp = client.get("/search?q=hello", follow_redirects=False)
    assert resp.status_code == 401


def test_search_route_with_q_returns_200(client, auth_headers, monkeypatch):
    from app.services import search as search_mod

    async def _fake_search(lk, q):
        from app.services.search import SearchResult
        return [SearchResult(kind="room", title="test-room", subtitle="0 participants", url="/rooms/test-room", status="idle")]

    monkeypatch.setattr(search_mod, "search_all", _fake_search)
    resp = client.get("/search?q=test", headers=auth_headers)
    assert resp.status_code == 200
    assert b"test-room" in resp.content
