"""
Tests for Backend Cross-Camera Topology and Continuity Tracking Endpoints.

Covers:
1. GET /api/topology (retrieves camera nodes and transition edges)
2. POST /api/topology/edges (adds allowed physical transition with temporal constraints)
3. POST /api/tracking/cross-camera-evaluate (evaluates continuity: CONFIRMED, PROBABLE, UNCERTAIN with reasoning)
4. Teleportation / Impossible Speed detection
5. Disconnected Camera rejection
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

from main import app, verify_edge_node, topology_graph, continuity_tracker
from database import Base, get_db
from models import Camera


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
        cam1 = Camera(id="cam-gate", name="Main Gate", zone="Perimeter")
        cam2 = Camera(id="cam-lobby", name="Reception Lobby", zone="Building 1")
        cam3 = Camera(id="cam-vault", name="Secure Vault", zone="Building 2")
        db.add_all([cam1, cam2, cam3])
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


def test_get_topology(client):
    """GET /api/topology returns registered cameras as nodes."""
    response = client.get("/api/topology")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "cam-gate" in data["nodes"]
    assert "cam-lobby" in data["nodes"]


def test_add_topology_edge(client):
    """POST /api/topology/edges adds an allowed physical transition."""
    edge_payload = {
        "from_camera_id": "cam-gate",
        "to_camera_id": "cam-lobby",
        "min_travel_seconds": 5.0,
        "max_travel_seconds": 45.0,
        "typical_travel_seconds": 15.0,
        "distance_meters": 30.0,
        "transition_probability": 0.9,
        "bidirectional": True,
    }
    response = client.post("/api/topology/edges", json=edge_payload)
    assert response.status_code == 200
    edge = response.json()
    assert edge["from_camera_id"] == "cam-gate"
    assert edge["to_camera_id"] == "cam-lobby"
    assert edge["min_travel_seconds"] == 5.0
    assert edge["max_travel_seconds"] == 45.0


def test_evaluate_confirmed_transition(client):
    """POST /api/tracking/cross-camera-evaluate with plausible time & high similarity returns CONFIRMED."""
    # Ensure edge is configured
    client.post("/api/topology/edges", json={
        "from_camera_id": "cam-gate",
        "to_camera_id": "cam-lobby",
        "min_travel_seconds": 5.0,
        "max_travel_seconds": 45.0,
        "typical_travel_seconds": 15.0,
        "bidirectional": True,
    })

    eval_payload = {
        "from_camera_id": "cam-gate",
        "to_camera_id": "cam-lobby",
        "elapsed_seconds": 14.0,
        "embedding_similarity": 0.85,
    }
    response = client.post("/api/tracking/cross-camera-evaluate", json=eval_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "CONFIRMED"
    assert data["topology_edge_exists"] is True
    assert data["is_teleportation"] is False
    assert data["temporal_score"] > 0.5
    assert "Confirmed transition" in data["explanation"]


def test_evaluate_teleportation_rejected(client):
    """POST /api/tracking/cross-camera-evaluate with impossible travel time returns UNCERTAIN."""
    eval_payload = {
        "from_camera_id": "cam-gate",
        "to_camera_id": "cam-lobby",
        "elapsed_seconds": 0.8,  # Below min 5.0s
        "embedding_similarity": 0.95,  # High face similarity should not bypass physics!
    }
    response = client.post("/api/tracking/cross-camera-evaluate", json=eval_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "UNCERTAIN"
    assert data["is_teleportation"] is True
    assert "teleportation" in data["explanation"].lower()


def test_evaluate_disconnected_cameras_rejected(client):
    """POST /api/tracking/cross-camera-evaluate on disconnected cameras returns UNCERTAIN."""
    eval_payload = {
        "from_camera_id": "cam-gate",
        "to_camera_id": "cam-vault",  # Disconnected camera in separate building
        "elapsed_seconds": 10.0,
        "embedding_similarity": 0.90,
    }
    response = client.post("/api/tracking/cross-camera-evaluate", json=eval_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "UNCERTAIN"
    assert data["topology_edge_exists"] is False
    assert "Unconnected" in data["explanation"]
