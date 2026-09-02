"""
Tests for Backend Cloud Vector Search and Gallery Versioning Endpoints.

Covers:
1. GET /api/internal/gallery (returns active gallery with version number and profile IDs)
2. POST /api/internal/vector-search (performs cloud vector search returning top candidates)
3. Cloud search threshold filtering
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

from main import app, verify_edge_node
from database import Base, get_db
from models import Profile, Embedding, ProfileRole


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
        # Create enrolled profile with embedding
        np.random.seed(42)
        v_alice = np.random.randn(512).astype(np.float32)
        v_alice /= np.linalg.norm(v_alice)
        
        v_bob = np.random.randn(512).astype(np.float32)
        v_bob /= np.linalg.norm(v_bob)

        p1 = Profile(id="prof-1", name="Alice Wonderland", role=ProfileRole.employee, embedding_count=1)
        emb1 = Embedding(id="emb-1", profile_id="prof-1", vector=v_alice.tolist())

        p2 = Profile(id="prof-2", name="Bob Builder", role=ProfileRole.vip, embedding_count=1)
        emb2 = Embedding(id="emb-2", profile_id="prof-2", vector=v_bob.tolist())

        db.add_all([p1, emb1, p2, emb2])
        db.commit()
        yield db, v_alice, v_bob
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
        yield test_client, db_session[1], db_session[2]
    app.dependency_overrides.clear()


def test_get_gallery_versioned(client):
    """GET /api/internal/gallery returns versioned gallery and labels."""
    test_client, _, _ = client
    response = test_client.get("/api/internal/gallery", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "labels" in data
    assert "Alice Wonderland" in data["labels"]
    assert "Bob Builder" in data["labels"]
    assert len(data["embeddings"]) == 2


def test_cloud_vector_search_match(client):
    """POST /api/internal/vector-search finds enrolled profile accurately."""
    test_client, v_alice, _ = client

    # Query with Alice's vector + slight noise (sim ~0.95)
    noise = np.random.randn(512).astype(np.float32)
    noise /= np.linalg.norm(noise)
    q = 0.95 * v_alice + 0.05 * noise
    q /= np.linalg.norm(q)

    search_payload = {
        "embedding": q.tolist(),
        "top_k": 1,
        "threshold": 0.50,
    }
    response = test_client.post(
        "/api/internal/vector-search",
        json=search_payload,
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data
    assert len(data["matches"]) == 1
    match = data["matches"][0]
    assert match["identity"] == "Alice Wonderland"
    assert match["score"] > 0.85
    assert "search_latency_ms" in data


def test_cloud_vector_search_no_match_below_threshold(client):
    """Unknown vector below threshold returns empty matches."""
    test_client, _, _ = client
    random_vec = np.random.randn(512).astype(np.float32)
    random_vec /= np.linalg.norm(random_vec)

    search_payload = {
        "embedding": random_vec.tolist(),
        "top_k": 1,
        "threshold": 0.75,
    }
    response = test_client.post(
        "/api/internal/vector-search",
        json=search_payload,
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["matches"]) == 0
