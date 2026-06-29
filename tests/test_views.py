"""Tests for saved views service and routes."""

import pytest
from unittest.mock import patch


def _csrf():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


# ---------------------------------------------------------------------------
# Service tests (patch _STORE_PATH directly — it's a module-level constant)
# ---------------------------------------------------------------------------

def test_list_views_empty(tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        assert sv.list_views() == []


def test_create_view_basic(tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        view = sv.create_view(name="My View", time_range="1h")
        assert view.name == "My View"
        assert view.time_range == "1h"
        assert len(view.id) == 8


def test_create_view_persisted(tmp_path):
    import app.services.saved_views as sv
    path = str(tmp_path / "views.json")
    with patch.object(sv, "_STORE_PATH", path):
        sv.create_view(name="Persist me")
        views = sv.list_views()
    assert len(views) == 1
    assert views[0].name == "Persist me"


def test_get_view_found(tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        created = sv.create_view(name="Find me")
        found = sv.get_view(created.id)
    assert found is not None
    assert found.name == "Find me"


def test_get_view_not_found(tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        assert sv.get_view("nonexistent") is None


def test_delete_view_removes_it(tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        v = sv.create_view(name="Delete me")
        result = sv.delete_view(v.id)
        remaining = sv.list_views()
    assert result is True
    assert remaining == []


def test_delete_view_not_found(tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        assert sv.delete_view("bad-id") is False


def test_view_as_query_string_empty():
    from app.services.saved_views import SavedView
    v = SavedView(id="abc", name="n")
    assert v.as_query_string() == ""


def test_view_as_query_string_with_filters():
    from app.services.saved_views import SavedView
    v = SavedView(id="abc", name="n", time_range="1h", q="test", sort="asc")
    qs = v.as_query_string()
    assert "time_range=1h" in qs
    assert "q=test" in qs
    assert "sort=asc" in qs


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_views_page_returns_200(client, auth_headers, tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        resp = client.get("/views", headers=auth_headers)
    assert resp.status_code == 200


def test_views_page_requires_auth(client):
    resp = client.get("/views", follow_redirects=False)
    assert resp.status_code == 401


def test_create_view_via_route(client, auth_headers, tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        resp = client.post(
            "/views",
            data={
                "csrf_token": _csrf(),
                "name": "Route view",
                "time_range": "24h",
                "q": "",
                "sort": "desc",
                "sort_by": "created_at",
            },
            headers=auth_headers,
            follow_redirects=False,
        )
    assert resp.status_code == 303


def test_delete_view_via_route(client, auth_headers, tmp_path):
    import app.services.saved_views as sv
    with patch.object(sv, "_STORE_PATH", str(tmp_path / "views.json")):
        v = sv.create_view(name="To delete")
        resp = client.post(
            f"/views/{v.id}/delete",
            data={"csrf_token": _csrf()},
            headers=auth_headers,
            follow_redirects=False,
        )
    assert resp.status_code == 303
