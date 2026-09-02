import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ["DATABASE_URL"] = "sqlite:///./test_reconciliation.db"

from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app, verify_edge_node
from database import Base, get_db
from models import Detection, SequenceAcknowledgment

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_reconciliation.db"
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

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_edge_node] = override_verify_edge_node

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_edge_node] = override_verify_edge_node
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def insert_detection(db, device_id, camera_id, sequence_number):
    import uuid
    det = Detection(
        id=str(uuid.uuid4()),
        camera_id=camera_id,
        profile_id=None,
        timestamp=datetime.now(timezone.utc),
        status="unknown",
        confidence=0.9,
        bbox="[0,0,0,0]",
        event_id=f"evt-{device_id}-{camera_id}-{sequence_number}",
        device_id=device_id,
        sequence_number=sequence_number
    )
    db.add(det)
    db.commit()

def test_missing_middle_event():
    """Test when a single event in the middle is missing."""
    db = TestingSessionLocal()
    # Insert 1, 3 (2 is missing)
    insert_detection(db, "device-1", "cam-1", 1)
    insert_detection(db, "device-1", "cam-1", 3)
    
    import uuid
    # Set backend ack to 0 just in case
    ack = SequenceAcknowledgment(
        id=str(uuid.uuid4()),
        device_id="device-1", 
        camera_id="cam-1", 
        last_acknowledged_sequence=0, 
        last_updated=datetime.now(timezone.utc)
    )
    db.add(ack)
    db.commit()
    db.close()
    
    payload = {
        "device_id": "device-1",
        "cameras": [
            {
                "camera_id": "cam-1",
                "highest_local_sequence": 3,
                "lowest_pending_sequence": None,
                "last_completed_sequence": 3
            }
        ]
    }
    
    resp = client.post("/api/detections/reconcile", json=payload, headers={"X-API-Key": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["reconciled_cameras"]) == 1
    cam = data["reconciled_cameras"][0]
    assert cam["camera_id"] == "cam-1"
    assert cam["missing_ranges"] == [[2, 2]]

def test_missing_range():
    """Test when a block of events is missing."""
    db = TestingSessionLocal()
    # Insert 1, 6 (2,3,4,5 missing)
    insert_detection(db, "device-1", "cam-1", 1)
    insert_detection(db, "device-1", "cam-1", 6)
    db.close()
    
    payload = {
        "device_id": "device-1",
        "cameras": [
            {
                "camera_id": "cam-1",
                "highest_local_sequence": 6,
                "lowest_pending_sequence": None,
                "last_completed_sequence": 6
            }
        ]
    }
    
    resp = client.post("/api/detections/reconcile", json=payload, headers={"X-API-Key": "test"})
    assert resp.status_code == 200
    data = resp.json()
    cam = data["reconciled_cameras"][0]
    assert cam["missing_ranges"] == [[2, 5]]

def test_duplicate_range():
    """Test when no events are missing."""
    db = TestingSessionLocal()
    # Insert 1,2,3
    insert_detection(db, "device-1", "cam-1", 1)
    insert_detection(db, "device-1", "cam-1", 2)
    insert_detection(db, "device-1", "cam-1", 3)
    db.close()
    
    payload = {
        "device_id": "device-1",
        "cameras": [
            {
                "camera_id": "cam-1",
                "highest_local_sequence": 3,
                "lowest_pending_sequence": None,
                "last_completed_sequence": 3
            }
        ]
    }
    
    resp = client.post("/api/detections/reconcile", json=payload, headers={"X-API-Key": "test"})
    assert resp.status_code == 200
    data = resp.json()
    cam = data["reconciled_cameras"][0]
    assert cam["missing_ranges"] == []

def test_server_restart():
    """Test when server restarts and loses ack state but has detections."""
    db = TestingSessionLocal()
    # Insert 1, 2, 3, 4, 5
    for i in range(1, 6):
        insert_detection(db, "device-1", "cam-1", i)
        
    # Notice no SequenceAcknowledgment exists because it was lost
    db.close()
    
    payload = {
        "device_id": "device-1",
        "cameras": [
            {
                "camera_id": "cam-1",
                "highest_local_sequence": 5,
                "lowest_pending_sequence": None,
                "last_completed_sequence": 5
            }
        ]
    }
    
    resp = client.post("/api/detections/reconcile", json=payload, headers={"X-API-Key": "test"})
    assert resp.status_code == 200
    data = resp.json()
    cam = data["reconciled_cameras"][0]
    assert cam["missing_ranges"] == []
