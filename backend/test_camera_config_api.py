"""
Tests for Backend Per-Camera Configuration Endpoints.

Covers:
1. GET /api/cameras/{camera_id}/config (auto-generates default v1 if none exists)
2. PUT /api/cameras/{camera_id}/config (updates thresholds and increments version)
3. POST /api/cameras/{camera_id}/config/rollback (reverts to previous version parameters with new incremented version)
4. GET /api/cameras/{camera_id}/config/history (returns audit trail of all configuration versions)
5. Camera A and Camera B have completely distinct configurations
"""

import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app, verify_edge_node
from database import Base, get_db
from models import Camera, CameraConfig


# Setup in-memory test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        # Create test cameras
        cam_a = Camera(id="cam-a", name="Camera A", zone="Main Entrance")
        cam_b = Camera(id="cam-b", name="Camera B", zone="Warehouse")
        db.add_all([cam_a, cam_b])
        db.commit()
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_default_config(client):
    """GET config on a camera without a prior config creates a default version 1."""
    response = client.get("/api/cameras/cam-a/config")
    assert response.status_code == 200
    data = response.json()
    assert data["camera_id"] == "cam-a"
    assert data["version"] == 1
    assert data["is_active"] is True
    assert data["detection_threshold"] == 0.50
    assert data["recognition_threshold"] == 0.35


def test_update_config_increments_version(client):
    """PUT config updates thresholds and records a new version."""
    # First get creates v1
    client.get("/api/cameras/cam-a/config")

    # Update with new values
    update_payload = {
        "detection_threshold": 0.65,
        "recognition_threshold": 0.50,
        "sampling_rate": 2,
        "temporal_window": 4.0,
        "notes": "Tuned for bright outdoor lighting",
    }
    response = client.put("/api/cameras/cam-a/config", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
    assert data["detection_threshold"] == 0.65
    assert data["recognition_threshold"] == 0.50
    assert data["sampling_rate"] == 2
    assert data["temporal_window"] == 4.0
    assert data["notes"] == "Tuned for bright outdoor lighting"


def test_rollback_configuration(client):
    """Rollback creates a new version containing the target older version's settings."""
    # v1 (default)
    client.get("/api/cameras/cam-a/config")

    # v2
    client.put("/api/cameras/cam-a/config", json={
        "detection_threshold": 0.75,
        "recognition_threshold": 0.60,
    })

    # Rollback to v1
    response = client.post("/api/cameras/cam-a/config/rollback", json={"target_version": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 3  # increments version for auditability
    assert data["detection_threshold"] == 0.50
    assert data["recognition_threshold"] == 0.35
    assert "Rollback to version 1" in data["notes"]


def test_camera_config_history(client):
    """Audit history returns all versions in descending order."""
    client.get("/api/cameras/cam-a/config")  # v1
    client.put("/api/cameras/cam-a/config", json={"detection_threshold": 0.60})  # v2
    client.put("/api/cameras/cam-a/config", json={"detection_threshold": 0.70})  # v3

    response = client.get("/api/cameras/cam-a/config/history")
    assert response.status_code == 200
    res_data = response.json()
    assert "history" in res_data
    history = res_data["history"]
    assert len(history) == 3
    assert history[0]["version"] == 3
    assert history[1]["version"] == 2
    assert history[2]["version"] == 1


def test_distinct_cameras_have_independent_configs(client):
    """Camera A and Camera B configurations operate in complete isolation."""
    # Config Camera A
    client.put("/api/cameras/cam-a/config", json={
        "detection_threshold": 0.80,
        "recognition_threshold": 0.60,
        "sampling_rate": 1,
        "temporal_window": 2.0,
    })

    # Config Camera B
    client.put("/api/cameras/cam-b/config", json={
        "detection_threshold": 0.30,
        "recognition_threshold": 0.20,
        "sampling_rate": 4,
        "temporal_window": 6.0,
    })

    cfg_a = client.get("/api/cameras/cam-a/config").json()
    cfg_b = client.get("/api/cameras/cam-b/config").json()

    assert cfg_a["detection_threshold"] == 0.80
    assert cfg_b["detection_threshold"] == 0.30
    assert cfg_a["recognition_threshold"] == 0.60
    assert cfg_b["recognition_threshold"] == 0.20
    assert cfg_a["sampling_rate"] == 1
    assert cfg_b["sampling_rate"] == 4
