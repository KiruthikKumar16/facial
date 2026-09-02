"""
Tests for Backend Node Health & Adaptive Runtime Reporting Endpoints.

Covers:
1. POST /api/nodes/health (ingests live metrics, mode, and decision logs from edge node)
2. GET /api/nodes/health (retrieves active health reports across all edge nodes)
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

from main import app, verify_edge_node, node_health_store
from database import Base, get_db


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

    def override_verify():
        return "test-api-key"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_edge_node] = override_verify
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_post_and_get_node_health(client):
    """Edge node can post health metrics and retrieve via aggregated GET endpoint."""
    report_payload = {
        "device_id": "edge-gate-01",
        "camera_id": "cam-gate",
        "mode": "THROTTLED_COMPUTE",
        "metrics": {
            "cpu_percent": 88.5,
            "memory_percent": 65.0,
            "disk_free_mb": 4200.0,
            "camera_fps": 30.0,
            "inference_fps": 10.0,
            "network_latency_ms": 35.0,
            "is_online": True,
            "recognition_latency_ms": 42.0,
        },
        "decisions": [
            {
                "previous_mode": "NORMAL",
                "new_mode": "THROTTLED_COMPUTE",
                "trigger_reason": "High CPU 88.5%",
                "applied_parameters": {"frame_sampling_rate": 0.33},
            }
        ]
    }

    # 1. Post health report
    post_resp = client.post("/api/nodes/health", json=report_payload, headers={"X-API-Key": "test-key"})
    assert post_resp.status_code == 200
    assert post_resp.json()["status"] == "ok"

    # 2. Get all nodes health
    get_resp = client.get("/api/nodes/health")
    assert get_resp.status_code == 200
    nodes = get_resp.json()["nodes"]
    assert len(nodes) >= 1
    
    node = next((n for n in nodes if n["device_id"] == "edge-gate-01"), None)
    assert node is not None
    assert node["mode"] == "THROTTLED_COMPUTE"
    assert node["metrics"]["cpu_percent"] == 88.5
    assert len(node["decisions"]) == 1
