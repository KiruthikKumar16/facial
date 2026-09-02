"""
Tests for Backend Recognition Event Provenance Endpoints.

Covers:
1. Detection ingestion with full lineage provenance
2. GET /api/detections/{event_id}/provenance retrieving 7-stage lineage graph
3. Fallback provenance synthesis for legacy detections
4. POST /api/provenance/retention pruning expired provenance records
"""

import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app, verify_edge_node
from database import Base, get_db
from models import Camera, Profile, EventProvenance


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
    # Create test camera & profile
    cam = Camera(id="cam-prov-01", name="Main Entrance", rtsp_url="rtsp://localhost/stream")
    prof = Profile(id="prof-prov-01", name="Dr. Emily Thorne", role="employee", department="R&D")
    db.add_all([cam, prof])
    db.commit()
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


def test_detection_creation_and_provenance_query(client):
    """Detection with provenance metadata creates traceable 7-stage lineage graph."""
    det_payload = {
        "camera_id": "cam-prov-01",
        "identity": "Dr. Emily Thorne",
        "confidence": 0.96,
        "bbox": [100, 100, 250, 250],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": "evt-prov-test-01",
        "device_id": "edge-gate-01",
        "sequence_number": 1,
        "provenance": {
            "frame_reference": "frm_cam-prov-01_1720000000000_01",
            "track_id": "track_cam-prov-01_001",
            "observation_references": ["obs_01", "obs_02"],
            "embedding_fingerprint": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "candidate_matches": [
                {"identity": "Dr. Emily Thorne", "score": 0.96, "profile_id": "prof-prov-01", "rank": 1},
                {"identity": "Jane Doe", "score": 0.41, "profile_id": "prof-jane-02", "rank": 2},
            ],
            "decision_tier": "LOCAL_HIGH_CONFIDENCE",
            "sync_event_id": "sync_evt-prov-test-01",
            "provenance_chain_hash": "a1b2c3d4e5f600112233445566778899aabbccddeeff00112233445566778899",
        }
    }

    # 1. Ingest detection
    resp = client.post("/api/detections", json=det_payload, headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200

    # 2. Query provenance
    prov_resp = client.get("/api/detections/evt-prov-test-01/provenance")
    assert prov_resp.status_code == 200
    prov_data = prov_resp.json()

    assert prov_data["event_id"] == "evt-prov-test-01"
    assert prov_data["camera_id"] == "cam-prov-01"
    assert prov_data["frame_reference"] == "frm_cam-prov-01_1720000000000_01"
    assert prov_data["track_id"] == "track_cam-prov-01_001"
    assert len(prov_data["observation_references"]) == 2
    assert len(prov_data["candidate_matches"]) == 2
    assert prov_data["selected_identity"] == "Dr. Emily Thorne"
    assert prov_data["confidence"] == 0.96

    # Verify 7 stages
    stages = prov_data["stages"]
    assert len(stages) == 7
    stage_names = [s["stage_name"] for s in stages]
    assert any("Camera Ingestion" in s for s in stage_names)
    assert any("Frame Acquisition" in s for s in stage_names)
    assert any("Face Tracking" in s for s in stage_names)
    assert any("Embedding Extraction" in s for s in stage_names)
    assert any("Candidate Evaluation" in s for s in stage_names)
    assert any("Recognition Decision" in s for s in stage_names)
    assert any("Cloud Synchronization" in s for s in stage_names)


def test_provenance_fallback_for_legacy_detections(client):
    """Legacy detection without stored provenance metadata returns synthesized fallback lineage."""
    legacy_payload = {
        "camera_id": "cam-prov-01",
        "identity": "Dr. Emily Thorne",
        "confidence": 0.88,
        "bbox": [50, 50, 150, 150],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": "evt-legacy-synthesized-01",
        "device_id": "edge-gate-01",
        "sequence_number": 2,
    }
    resp = client.post("/api/detections", json=legacy_payload, headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200

    prov_resp = client.get("/api/detections/evt-legacy-synthesized-01/provenance")
    assert prov_resp.status_code == 200
    prov_data = prov_resp.json()
    assert prov_data["event_id"] == "evt-legacy-synthesized-01"
    assert len(prov_data["stages"]) == 7


def test_provenance_retention_policy_enforcement(client, db_session):
    """Enforcing retention policy deletes lineage older than cutoff while keeping detection intact."""
    # Insert an old provenance record (> 30 days old)
    old_time = datetime.now(timezone.utc) - timedelta(days=45)
    
    # First insert detection
    det_payload = {
        "camera_id": "cam-prov-01",
        "identity": "Dr. Emily Thorne",
        "confidence": 0.90,
        "bbox": [20, 20, 80, 80],
        "timestamp": old_time.isoformat(),
        "event_id": "evt-old-retention-01",
        "device_id": "edge-gate-01",
        "sequence_number": 3,
    }
    client.post("/api/detections", json=det_payload, headers={"X-API-Key": "test-key"})

    # Manually backdate the created_at on provenance record
    prov = db_session.query(EventProvenance).filter(EventProvenance.event_id == "evt-old-retention-01").first()
    if prov:
        prov.created_at = old_time
        db_session.commit()

    # Enforce retention with max_retention_days = 30
    ret_resp = client.post("/api/provenance/retention", json={"max_retention_days": 30})
    assert ret_resp.status_code == 200
    ret_data = ret_resp.json()
    assert ret_data["purged_records_count"] >= 1
