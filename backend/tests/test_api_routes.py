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
