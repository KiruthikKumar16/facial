import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone



from main import app, verify_edge_node
from database import Base, get_db

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

def override_verify_edge_node():
    return "test-api-key"

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_edge_node] = override_verify_edge_node
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()

def test_sync_sequence_normal():
    response = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-1",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sync_info"]["is_duplicate"] is False
    assert data["sync_info"]["is_out_of_order"] is False
    assert data["sync_info"]["is_gap_detected"] is False
    assert data["sync_info"]["last_acknowledged_sequence"] == 1

def test_sync_sequence_duplicate():
    # Send seq 1
    client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-1",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    
    # Send seq 1 again (different event_id to bypass idempotency check and test sequence duplicate check)
    response = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-2",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sync_info"]["is_duplicate"] is True
    assert data["sync_info"]["is_out_of_order"] is False
    assert data["sync_info"]["last_acknowledged_sequence"] == 1

def test_sync_sequence_out_of_order():
    # Send seq 2 first
    client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-2",
            "device_id": "device-1",
            "sequence_number": 2
        },
        headers={"X-API-Key": "test-api-key"}
    )
    
    # Send seq 1 (out of order)
    response = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-1",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sync_info"]["is_duplicate"] is False
    assert data["sync_info"]["is_out_of_order"] is True
    assert data["sync_info"]["is_gap_detected"] is False
    # last_acknowledged_sequence stays at 2 because 1 is <= 2
    assert data["sync_info"]["last_acknowledged_sequence"] == 2

def test_sync_sequence_gap():
    # Send seq 1
    client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-1",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    
    # Send seq 3 (gap)
    response = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-8",
            "device_id": "device-1",
            "sequence_number": 3
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sync_info"]["is_gap_detected"] is True
    assert data["sync_info"]["last_acknowledged_sequence"] == 3

def test_sync_sequence_idempotency():
    # Send seq 1
    resp1 = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-1",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert resp1.status_code == 200
    
    # Retransmit exact same payload
    resp2 = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-1",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert resp2.status_code == 200
    data = resp2.json()
    # It should have sync_info attached, and it shouldn't log as duplicate because it hit idempotency check first
    assert "sync_info" in data
    assert data["sync_info"]["is_duplicate"] is True
