import os
os.environ["DATABASE_URL"] = "sqlite:///./test_idempotent.db"

import pytest
import threading
import time
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app, verify_edge_node
from database import Base, get_db
from models import Detection

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_idempotent.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30.0}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()

def test_missing_event_id_rejected():
    """Ensure HTTP 422 is returned if event_id is missing."""
    response = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # event_id is missing
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 422
    assert "event_id" in response.text

def test_normal_insert_returns_inserted_true():
    """First time ingestion returns inserted=True."""
    response = client.post(
        "/api/detections",
        json={
            "camera_id": "cam-1",
            "identity": "Person A",
            "confidence": 0.9,
            "bbox": [10, 10, 50, 50],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": "event-100",
            "device_id": "device-1",
            "sequence_number": 1
        },
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["inserted"] is True
    assert data["event_id"] == "event-100"

def test_exact_duplicate_returns_inserted_false():
    """Retransmission returns inserted=False with the same database ID."""
    payload = {
        "camera_id": "cam-1",
        "identity": "Person A",
        "confidence": 0.9,
        "bbox": [10, 10, 50, 50],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": "event-200",
        "device_id": "device-1",
        "sequence_number": 1
    }
    
    # First call
    resp1 = client.post("/api/detections", json=payload, headers={"X-API-Key": "test-api-key"})
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["inserted"] is True
    
    # Second call (exact duplicate)
    resp2 = client.post("/api/detections", json=payload, headers={"X-API-Key": "test-api-key"})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["inserted"] is False
    assert data2["id"] == data1["id"]

def test_idempotent_concurrent_duplicates():
    """Concurrent submissions with the same event_id result in exactly 1 row."""
    payload = {
        "camera_id": "cam-1",
        "identity": "Person A",
        "confidence": 0.9,
        "bbox": [10, 10, 50, 50],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": "event-concurrent",
        "device_id": "device-1",
        "sequence_number": 1
    }
    
    responses = []
    
    def submit_request():
        # Spin up a client manually per thread to avoid shared socket state issues
        with TestClient(app) as thread_client:
            res = thread_client.post("/api/detections", json=payload, headers={"X-API-Key": "test-api-key"})
            responses.append(res)
            
    threads = [threading.Thread(target=submit_request) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    assert len(responses) == 10
    for r in responses:
        assert r.status_code == 200
        
    # Check that exactly ONE response had inserted=True
    inserted_true_count = sum(1 for r in responses if r.json().get("inserted") is True)
    assert inserted_true_count == 1
    
    # Check that all other responses had inserted=False
    inserted_false_count = sum(1 for r in responses if r.json().get("inserted") is False)
    assert inserted_false_count == 9
    
    # Check the database has exactly one row
    db = TestingSessionLocal()
    count = db.query(Detection).filter(Detection.event_id == "event-concurrent").count()
    assert count == 1
    db.close()

def test_network_timeout_retry_safe():
    """Simulate retry sequence when network times out before 2xx is received."""
    payload = {
        "camera_id": "cam-1",
        "identity": "Person A",
        "confidence": 0.9,
        "bbox": [10, 10, 50, 50],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": "event-timeout-retry",
        "device_id": "device-1",
        "sequence_number": 1
    }
    
    # 1. Edge sends, server receives and commits, but connection drops before response
    resp1 = client.post("/api/detections", json=payload, headers={"X-API-Key": "test-api-key"})
    assert resp1.status_code == 200
    assert resp1.json()["inserted"] is True
    
    # Edge didn't get response due to timeout. Edge retries later.
    resp2 = client.post("/api/detections", json=payload, headers={"X-API-Key": "test-api-key"})
    assert resp2.status_code == 200
    assert resp2.json()["inserted"] is False
    
    db = TestingSessionLocal()
    count = db.query(Detection).filter(Detection.event_id == "event-timeout-retry").count()
    assert count == 1
    db.close()
