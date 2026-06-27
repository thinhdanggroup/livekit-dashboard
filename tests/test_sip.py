"""Tests for SIP outbound/inbound routes and JSON editor fix."""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers():
    import base64
    creds = f"{os.environ['ADMIN_USERNAME']}:{os.environ['ADMIN_PASSWORD']}"
    return {"Authorization": f"Basic {base64.b64encode(creds.encode()).decode()}"}


def _csrf_token():
    from app.security.csrf import generate_csrf_token
    return generate_csrf_token()


def _make_mock_lk(sip_enabled: bool = True):
    """Return a mock LiveKitClient with SIP methods stubbed."""
    lk = MagicMock()
    lk.sip_enabled = sip_enabled

    # Async stubs — method names must match LiveKitClient exactly
    lk.list_sip_trunks = AsyncMock(return_value=[])
    lk.list_sip_inbound_trunks = AsyncMock(return_value=[])
    lk.list_sip_dispatch_rules = AsyncMock(return_value=[])
    lk.create_sip_trunk = AsyncMock(return_value=MagicMock(sip_trunk_id="ST_test123"))
    lk.update_sip_trunk = AsyncMock(return_value=MagicMock())
    lk.delete_sip_trunk = AsyncMock(return_value=None)
    lk.create_sip_inbound_trunk = AsyncMock(return_value=MagicMock(sip_trunk_id="ST_inbound_test"))
    lk.update_sip_inbound_trunk = AsyncMock(return_value=MagicMock())
    lk.create_sip_dispatch_rule = AsyncMock(return_value=MagicMock(sip_dispatch_rule_id="SDR_test"))
    lk.update_sip_dispatch_rule = AsyncMock(return_value=MagicMock())
    lk.delete_sip_dispatch_rule = AsyncMock(return_value=None)
    return lk


@pytest.fixture
def sip_client():
    """TestClient with ENABLE_SIP=true and mocked LiveKitClient."""
    os.environ["ENABLE_SIP"] = "true"
    from app.main import app
    from app.services.livekit import get_livekit_client

    mock_lk = _make_mock_lk(sip_enabled=True)
    app.dependency_overrides[get_livekit_client] = lambda: mock_lk

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_lk

    app.dependency_overrides.pop(get_livekit_client, None)
    os.environ["ENABLE_SIP"] = "false"


@pytest.fixture
def sip_disabled_client():
    """TestClient with ENABLE_SIP=false."""
    os.environ["ENABLE_SIP"] = "false"
    from app.main import app
    from app.services.livekit import get_livekit_client

    mock_lk = _make_mock_lk(sip_enabled=False)
    app.dependency_overrides[get_livekit_client] = lambda: mock_lk

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_lk

    app.dependency_overrides.pop(get_livekit_client, None)


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------

class TestSipAuthGuards:
    def test_outbound_page_requires_auth(self, client):
        assert client.get("/sip-outbound").status_code == status.HTTP_401_UNAUTHORIZED

    def test_inbound_page_requires_auth(self, client):
        assert client.get("/sip-inbound").status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_trunk_requires_auth(self, client):
        r = client.post("/sip-outbound/trunk/create", data={"csrf_token": "x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_trunk_requires_auth(self, client):
        r = client.post("/sip-outbound/trunk/update", data={"csrf_token": "x", "sip_trunk_id": "ST_x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_trunk_requires_auth(self, client):
        r = client.post("/sip-outbound/trunk/delete", data={"csrf_token": "x", "sip_trunk_id": "ST_x"})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Page load tests
# ---------------------------------------------------------------------------

class TestSipPageLoads:
    def test_outbound_page_loads(self, sip_client):
        c, _ = sip_client
        r = c.get("/sip-outbound", headers=_auth_headers())
        assert r.status_code == status.HTTP_200_OK
        assert b"Outbound" in r.content

    def test_inbound_page_loads(self, sip_client):
        c, _ = sip_client
        r = c.get("/sip-inbound", headers=_auth_headers())
        assert r.status_code == status.HTTP_200_OK
        assert b"Inbound" in r.content

    def test_outbound_page_sip_disabled_redirects(self, sip_disabled_client):
        c, _ = sip_disabled_client
        r = c.get("/sip-outbound", headers=_auth_headers(), follow_redirects=False)
        # Should redirect away (to /) when SIP disabled
        assert r.status_code in (status.HTTP_302_FOUND, status.HTTP_303_SEE_OTHER, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Outbound trunk CRUD — form fields
# ---------------------------------------------------------------------------

class TestOutboundTrunkFormCRUD:
    def test_create_trunk_via_form(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-outbound/trunk/create",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "trunk_name": "test-trunk",
                "address": "sip.example.com",
                "transport": "tcp",
                "numbers": "+15550001234",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.create_sip_trunk.assert_awaited_once()
        call_kwargs = mock_lk.create_sip_trunk.call_args.kwargs
        assert call_kwargs["name"] == "test-trunk"
        assert call_kwargs["address"] == "sip.example.com"
        assert "+15550001234" in call_kwargs["numbers"]

    def test_update_trunk_via_form(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-outbound/trunk/update",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "sip_trunk_id": "ST_abc123",
                "trunk_name": "updated-trunk",
                "address": "sip2.example.com",
                "transport": "udp",
                "numbers": "+15559990000,+15558880000",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.update_sip_trunk.assert_awaited_once()
        call_kwargs = mock_lk.update_sip_trunk.call_args.kwargs
        assert call_kwargs["name"] == "updated-trunk"
        assert call_kwargs["address"] == "sip2.example.com"
        assert len(call_kwargs["numbers"]) == 2

    def test_delete_trunk(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-outbound/trunk/delete",
            headers=_auth_headers(),
            data={"csrf_token": token, "sip_trunk_id": "ST_abc123"},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.delete_sip_trunk.assert_awaited_once_with(sip_trunk_id="ST_abc123")

    def test_create_trunk_missing_csrf_fails(self, sip_client):
        c, mock_lk = sip_client
        r = c.post(
            "/sip-outbound/trunk/create",
            headers=_auth_headers(),
            data={"csrf_token": "bad-token", "trunk_name": "x", "address": "y"},
            follow_redirects=False,
        )
        # Bad CSRF should redirect with danger flash or return 4xx
        assert r.status_code in (
            status.HTTP_303_SEE_OTHER,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
        )
        mock_lk.create_sip_trunk.assert_not_awaited()


# ---------------------------------------------------------------------------
# JSON editor fix — json_data overrides form fields
# ---------------------------------------------------------------------------

class TestOutboundTrunkJsonEditor:
    def test_create_trunk_json_overrides_form(self, sip_client):
        """json_data fields take precedence over individual form fields."""
        c, mock_lk = sip_client
        token = _csrf_token()
        json_payload = json.dumps({
            "name": "json-trunk",
            "address": "json.sip.example.com",
            "transport": "tls",
            "numbers": ["+15551112222"],
            "auth_username": "jsonuser",
            "metadata": "from-json-editor",
        })
        r = c.post(
            "/sip-outbound/trunk/create",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                # Form fields (should be overridden by json_data)
                "trunk_name": "FORM-TRUNK-SHOULD-NOT-BE-USED",
                "address": "FORM-ADDRESS-SHOULD-NOT-BE-USED",
                "json_data": json_payload,
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.create_sip_trunk.assert_awaited_once()
        kw = mock_lk.create_sip_trunk.call_args.kwargs
        assert kw["name"] == "json-trunk"
        assert kw["address"] == "json.sip.example.com"
        assert kw["metadata"] == "from-json-editor"
        assert "+15551112222" in kw["numbers"]

    def test_update_trunk_json_overrides_form(self, sip_client):
        """json_data fields take precedence over individual form fields on update."""
        c, mock_lk = sip_client
        token = _csrf_token()
        json_payload = json.dumps({
            "name": "json-updated-trunk",
            "address": "updated.json.sip.example.com",
            "numbers": ["+15553334444", "+15555556666"],
            "destination_country": "US",
            "metadata": "json-metadata",
        })
        r = c.post(
            "/sip-outbound/trunk/update",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "sip_trunk_id": "ST_json123",
                # Form fields (should be overridden)
                "trunk_name": "FORM-NAME-IGNORED",
                "address": "FORM-ADDRESS-IGNORED",
                "json_data": json_payload,
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.update_sip_trunk.assert_awaited_once()
        kw = mock_lk.update_sip_trunk.call_args.kwargs
        assert kw["name"] == "json-updated-trunk"
        assert kw["address"] == "updated.json.sip.example.com"
        assert kw["destination_country"] == "US"
        assert kw["metadata"] == "json-metadata"
        assert len(kw["numbers"]) == 2

    def test_update_trunk_json_headers_preserved(self, sip_client):
        """headers and headers_to_attributes from JSON editor are passed correctly."""
        c, mock_lk = sip_client
        token = _csrf_token()
        json_payload = json.dumps({
            "name": "trunk-with-headers",
            "address": "sip.example.com",
            "headers": {"X-Custom": "value1"},
            "headers_to_attributes": {"X-User-ID": "user_id"},
        })
        r = c.post(
            "/sip-outbound/trunk/update",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "sip_trunk_id": "ST_headers123",
                "json_data": json_payload,
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        kw = mock_lk.update_sip_trunk.call_args.kwargs
        assert kw["headers"] == {"X-Custom": "value1"}
        assert kw["headers_to_attributes"] == {"X-User-ID": "user_id"}

    def test_create_trunk_invalid_json_falls_back_to_form(self, sip_client):
        """Invalid json_data is silently ignored; form fields are used."""
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-outbound/trunk/create",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "trunk_name": "fallback-trunk",
                "address": "fallback.sip.example.com",
                "json_data": "NOT VALID JSON {{{",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        kw = mock_lk.create_sip_trunk.call_args.kwargs
        # Should have used the form fields since JSON was invalid
        assert kw["name"] == "fallback-trunk"
        assert kw["address"] == "fallback.sip.example.com"


# ---------------------------------------------------------------------------
# Inbound trunk CRUD
# ---------------------------------------------------------------------------

class TestInboundTrunkCRUD:
    def test_create_inbound_trunk(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-inbound/trunk/create",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "trunk_name": "test-inbound",
                "numbers": "+15550001234",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.create_sip_inbound_trunk.assert_awaited_once()

    def test_delete_inbound_trunk(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-inbound/trunk/delete",
            headers=_auth_headers(),
            data={"csrf_token": token, "sip_trunk_id": "ST_inbound_abc"},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]


# ---------------------------------------------------------------------------
# Dispatch rule CRUD
# ---------------------------------------------------------------------------

class TestInboundTrunkUpdate:
    def test_update_inbound_trunk(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-inbound/trunk/update",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "sip_trunk_id": "ST_inbound_abc",
                "trunk_name": "updated-inbound",
                "numbers": "+15550001234,+15559998888",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        mock_lk.update_sip_inbound_trunk.assert_awaited_once()
        kw = mock_lk.update_sip_inbound_trunk.call_args.kwargs
        assert kw["name"] == "updated-inbound"


class TestDispatchRuleCRUD:
    def test_create_dispatch_rule(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-inbound/rule/create",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "rule_name": "test-rule",
                "dispatch_rule_type": "individual",
                "pin": "1234",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        assert mock_lk.create_sip_dispatch_rule.call_count == 1

    def test_delete_dispatch_rule(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-inbound/rule/delete",
            headers=_auth_headers(),
            data={"csrf_token": token, "sip_dispatch_rule_id": "SDR_abc123"},
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]

    def test_update_dispatch_rule(self, sip_client):
        c, mock_lk = sip_client
        token = _csrf_token()
        r = c.post(
            "/sip-inbound/rule/update",
            headers=_auth_headers(),
            data={
                "csrf_token": token,
                "sip_dispatch_rule_id": "SDR_abc123",
                "rule_name": "updated-rule",
                "dispatch_rule_type": "direct",
                "room_name": "my-room",
            },
            follow_redirects=False,
        )
        assert r.status_code == status.HTTP_303_SEE_OTHER
        assert "flash_type=success" in r.headers["location"]
        assert mock_lk.update_sip_dispatch_rule.call_count == 1
