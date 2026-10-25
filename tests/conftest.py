"""Pytest configuration and fixtures"""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Setup test environment variables"""
    # Set test environment variables
    os.environ["LIVEKIT_URL"] = "http://localhost:7880"
    os.environ["LIVEKIT_API_KEY"] = "test-key"
    os.environ["LIVEKIT_API_SECRET"] = "test-secret"
    os.environ["ADMIN_USERNAME"] = "admin"
    os.environ["ADMIN_PASSWORD"] = "testpass"
    os.environ["APP_SECRET_KEY"] = "test-secret-key"
    os.environ["DEBUG"] = "true"
    os.environ["ENABLE_SIP"] = "false"


@pytest.fixture(autouse=True)
def _isolate_webhook_log(tmp_path, monkeypatch):
    """Point the webhook delivery log at a per-test tmp file so tests never
    read or write the real shared /tmp/webhook_log.json."""
    import app.services.webhook_log as wl

    monkeypatch.setattr(wl, "_STORE_PATH", str(tmp_path / "webhook_log.json"))


@pytest.fixture(autouse=True)
def _isolate_ghost_rooms(tmp_path, monkeypatch):
    """Point the ghost-room tracker at a per-test tmp file so tests never
    read or write the real shared /tmp/ghost_rooms.json, and so one test's
    polls don't leak ghosts into another test via /rooms."""
    import app.services.ghost_rooms as gr

    monkeypatch.setattr(gr, "_STORE_PATH", str(tmp_path / "ghost_rooms.json"))


@pytest.fixture(autouse=True)
def _isolate_ip_allowlist(tmp_path, monkeypatch):
    """Point the IP allowlist store at a per-test tmp file so tests never
    read or write the real shared /tmp/ip_allowlist.json. Without this, the
    full suite only passes by accident of that file not existing on a given
    machine -- a developer with a real allowlist saved locally would see
    every request from every test get 403'd."""
    import app.services.ip_allowlist as ipa

    monkeypatch.setattr(ipa, "_STORE_PATH", str(tmp_path / "ip_allowlist.json"))


@pytest.fixture(autouse=True)
def _isolate_security_log(tmp_path, monkeypatch):
    """Point the failed-login security log at a per-test tmp file so tests
    never read or write the real shared /tmp/security_log.json."""
    import app.services.security_log as sl

    monkeypatch.setattr(sl, "_STORE_PATH", str(tmp_path / "security_log.json"))


@pytest.fixture(autouse=True)
def _isolate_notifications(tmp_path, monkeypatch):
    """Point the notifications config store at a per-test tmp file so tests
    never read or write the real shared /tmp/notifications_config.json --
    the exact file a real locally-running dashboard would use."""
    import app.services.notifications as notifications

    monkeypatch.setattr(notifications, "_STORE_PATH", str(tmp_path / "notifications_config.json"))


@pytest.fixture(autouse=True)
def _isolate_report_rules(tmp_path, monkeypatch):
    """Point the report-rule store at a per-test tmp file so tests never
    read or write the real shared /tmp/report_rules.json. This matters even
    more than the other stores: the `client` fixture's lifespan startup now
    kicks off report_rules.run_scheduler_loop(), whose first tick calls
    run_due_rules() against _STORE_PATH -- without this isolation, a
    developer with stray due rules left from manual testing would trigger a
    real stats fetch and webhook POST on every single test's startup."""
    import app.services.report_rules as rr

    monkeypatch.setattr(rr, "_STORE_PATH", str(tmp_path / "report_rules.json"))


@pytest.fixture(autouse=True)
def _isolate_room_history(tmp_path, monkeypatch):
    """Point the room lifecycle history store at a per-test tmp file so tests
    never read or write the real shared /tmp/room_history.json. This matters
    even more than the other stores: the `client` fixture's lifespan startup
    now also kicks off room_poller.run_poller_loop(), whose first tick calls
    append_event()/prune_old() against _STORE_PATH -- without this isolation,
    a developer's real local room-history file would get written to (or
    read from) on every single test's startup."""
    import app.services.room_history as rh

    monkeypatch.setattr(rh, "_STORE_PATH", str(tmp_path / "room_history.json"))


@pytest.fixture
def client():
    """Create a test client"""
    from app.main import app
    
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    """Return basic auth headers for testing"""
    import base64
    
    credentials = f"{os.environ['ADMIN_USERNAME']}:{os.environ['ADMIN_PASSWORD']}"
    encoded = base64.b64encode(credentials.encode()).decode()
    
    return {"Authorization": f"Basic {encoded}"}

