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

