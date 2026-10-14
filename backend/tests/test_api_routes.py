import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent))

from fastapi.testclient import TestClient
from main import app
from auth import create_access_token

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


def test_analytics_footfall_with_date_range():
    """Verify /api/analytics/footfall does not crash with UnboundLocalError when date_from/date_to are provided."""
    token = create_access_token({"sub": "admin"})
    response = client.get(
        "/api/analytics/footfall?date_from=2026-10-14T00:00:00Z&date_to=2026-10-14T23:59:59Z",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 24
    assert all("hour" in b and "detections" in b for b in data)


def test_analytics_gender_distribution_with_date_range():
    """Verify /api/analytics/gender-distribution returns valid demographic slices with date filter."""
    token = create_access_token({"sub": "admin"})
    response = client.get(
        "/api/analytics/gender-distribution?date_from=2026-10-14T00:00:00Z&date_to=2026-10-14T23:59:59Z",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_analytics_attendance_with_date_range():
    """Verify /api/analytics/attendance returns valid records with date filter."""
    token = create_access_token({"sub": "admin"})
    response = client.get(
        "/api/analytics/attendance?date_from=2026-10-14T00:00:00Z&date_to=2026-10-14T23:59:59Z",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
