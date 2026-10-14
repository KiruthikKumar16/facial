import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    """Verify /health returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data

def test_unauthorized_dashboard_endpoints():
    """Verify that secured dashboard endpoints reject requests without token with 401."""
    response = client.get("/api/kpis")
    assert response.status_code == 401
    
    response = client.get("/api/cameras")
    assert response.status_code == 401

def test_auth_login_invalid_credentials():
    """Verify invalid login attempt returns 401."""
    response = client.post("/api/auth/login", data={"username": "wrong", "password": "bad"})
    assert response.status_code == 401


def test_websocket_unauthorized_rejection():
    """Verify connecting to WebSocket channels without token closes with 4001."""
    import pytest
    from starlette.websockets import WebSocketDisconnect
    
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/alerts") as ws:
            pass
    assert exc_info.value.code == 4001


def test_websocket_authorized_connection():
    """Verify connecting to WebSocket channels with valid JWT token succeeds."""
    from auth import create_access_token
    token = create_access_token({"sub": "admin"})
    with client.websocket_connect(f"/ws/alerts?token={token}") as ws:
        assert ws is not None


def test_cors_wildcard_origin():
    """Verify that requests from Vercel wildcard domains receive valid CORS headers."""
    response = client.options(
        "/health",
        headers={
            "Origin": "https://custom-preview-branch.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://custom-preview-branch.vercel.app"


def test_detect_endpoint_empty_payload():
    """Verify that /detect rejects empty payload appropriately."""
    response = client.post("/detect", files={})
    assert response.status_code == 422  # validation error for missing required file
