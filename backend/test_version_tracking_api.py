"""
Tests for Backend AI Model and Configuration Version Tracking API Endpoints.

Covers:
1. GET /api/system/version-bundle (returns active system version bundle)
2. POST /api/detections (persists all 6 version metadata fields in PostgreSQL/SQLite)
3. POST /api/internal/vector-search:
   - Filters out incompatible embedding models during migrations
   - Rejects unrecognized embedding models with 400 Bad Request
"""

import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app, verify_edge_node, active_version_bundle
from database import Base, get_db
from models import Profile, Embedding, ProfileRole, Detection


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
        np.random.seed(42)
        v_alice = np.random.randn(512).astype(np.float32)
        v_alice /= np.linalg.norm(v_alice)

        p1 = Profile(id="prof-alice", name="Alice Wonderland", role=ProfileRole.employee, embedding_count=1)
        emb1 = Embedding(id="emb-1", profile_id="prof-alice", vector=v_alice.tolist(), model_version="w600k_mbf_v1")

        # Incompatible model embedding from legacy system
        p2 = Profile(id="prof-legacy", name="Legacy Subject", role=ProfileRole.visitor, embedding_count=1)
        emb2 = Embedding(id="emb-2", profile_id="prof-legacy", vector=v_alice.tolist(), model_version="mobilenet_v2_256")

        db.add_all([p1, emb1, p2, emb2])
        db.commit()
        yield db, v_alice
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session[0]
        finally:
            pass

    def override_verify():
        return "test-api-key"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_edge_node] = override_verify
    with TestClient(app) as test_client:
        yield test_client, db_session[1]
    app.dependency_overrides.clear()


def test_get_system_version_bundle(client):
    """GET /api/system/version-bundle returns active version bundle and cryptographic hash."""
    test_client, _ = client
    response = test_client.get("/api/system/version-bundle")
    assert response.status_code == 200
    data = response.json()
    assert data["detection_model_version"] == active_version_bundle.detection_model_version
    assert data["embedding_model_version"] == active_version_bundle.embedding_model_version
    assert data["gallery_version"] == active_version_bundle.gallery_version
    assert data["threshold_version"] == active_version_bundle.threshold_version
    assert data["camera_config_version"] == active_version_bundle.camera_config_version
    assert data["algorithm_version"] == active_version_bundle.algorithm_version
    assert len(data["bundle_hash"]) == 64


def test_detection_creation_persists_version_metadata(client, db_session):
    """POST /api/detections records complete version bundle into database columns."""
    test_client, _ = client
    db, _ = db_session

    det_payload = {
        "camera_id": "cam-101",
        "identity": "Alice Wonderland",
        "confidence": 0.94,
        "bbox": [10, 20, 100, 150],
        "timestamp": "2026-09-01T12:30:00",
        "event_id": "evt-version-test-001",
        "detection_model_version": "scrfd_500m_bnkps_v1",
        "embedding_model_version": "w600k_mbf_v1",
        "gallery_version": 2,
        "threshold_version": 1,
        "camera_config_version": 3,
        "algorithm_version": "temporal_fusion_v2",
    }

    response = test_client.post("/api/detections", json=det_payload, headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["detection_model_version"] == "scrfd_500m_bnkps_v1"
    assert data["embedding_model_version"] == "w600k_mbf_v1"
    assert data["gallery_version"] == 2
    assert data["camera_config_version"] == 3
    assert data["version_bundle_hash"] is not None

    # Verify directly from DB record
    db_det = db.query(Detection).filter(Detection.event_id == "evt-version-test-001").first()
    assert db_det is not None
    assert db_det.detection_model_version == "scrfd_500m_bnkps_v1"
    assert db_det.embedding_model_version == "w600k_mbf_v1"
    assert db_det.gallery_version == 2
    assert db_det.camera_config_version == 3
    assert db_det.algorithm_version == "temporal_fusion_v2"


def test_vector_search_rejects_unsupported_model(client):
    """POST /api/internal/vector-search with invalid embedding model returns 400 Bad Request."""
    test_client, v_alice = client
    payload = {
        "embedding": v_alice.tolist(),
        "top_k": 1,
        "threshold": 0.50,
        "embedding_model_version": "unknown_experimental_model_v999",
    }
    response = test_client.post("/api/internal/vector-search", json=payload, headers={"X-API-Key": "test-key"})
    assert response.status_code == 400
    assert "Unrecognized or unsupported embedding model" in response.json()["detail"]


def test_vector_search_skips_incompatible_embeddings_during_migration(client):
    """Vector search skips embeddings with incompatible models, matching only valid models."""
    test_client, v_alice = client
    payload = {
        "embedding": v_alice.tolist(),
        "top_k": 5,
        "threshold": 0.50,
        "embedding_model_version": "w600k_mbf_v1",
    }
    response = test_client.post("/api/internal/vector-search", json=payload, headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    data = response.json()
    matches = data["matches"]
    assert len(matches) == 1
    assert matches[0]["identity"] == "Alice Wonderland"
    # Legacy Subject with model 'mobilenet_v2_256' was safely skipped
    assert not any(m["identity"] == "Legacy Subject" for m in matches)
