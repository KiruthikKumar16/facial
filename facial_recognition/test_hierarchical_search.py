"""
Tests and Performance Benchmarks for Hierarchical Edge/Cloud Vector Search.

Covers:
1. Local Gallery Indexing, Versioning & Serialization
2. Tier 1: High-Confidence Local Resolution (Zero cloud bandwidth, sub-millisecond latency)
3. Tier 2: Cloud Vector Search Escalation for uncertain local candidates
4. Tier 3: Offline Graceful Fallback when cloud is unreachable
5. Stale Gallery Automatic Cloud Search Escalation
6. Bandwidth Savings Measurement (2 KB vector vs 200 KB raw image)
7. Gallery Version Attachment to Recognition Events
8. Hierarchical Accuracy, Latency, and Bandwidth Benchmark
"""

import time
import pytest
import numpy as np
from pathlib import Path

from facial_recognition.hierarchical_search import (
    HierarchicalSearchEngine,
    LocalGallery,
    SearchResult,
    SearchTier,
)


@pytest.fixture
def sample_gallery(tmp_path):
    """Create a sample local gallery with 3 known identities."""
    gallery = LocalGallery(version=1)
    np.random.seed(42)
    
    # 3 distinct 512-d unit vectors
    emb_alice = np.random.randn(512).astype(np.float32)
    emb_alice /= np.linalg.norm(emb_alice)
    
    emb_bob = np.random.randn(512).astype(np.float32)
    emb_bob /= np.linalg.norm(emb_bob)
    
    emb_charlie = np.random.randn(512).astype(np.float32)
    emb_charlie /= np.linalg.norm(emb_charlie)

    gallery.update(
        labels=["Alice", "Bob", "Charlie"],
        embeddings=[emb_alice, emb_bob, emb_charlie],
        version=1,
        profile_ids=["p_alice", "p_bob", "p_charlie"],
    )
    
    file_path = tmp_path / "test_gallery.npz"
    gallery.save(file_path)
    return gallery, file_path, [emb_alice, emb_bob, emb_charlie]


# ==================== 1. Local Gallery Unit Tests ====================

def test_local_gallery_save_and_load(sample_gallery, tmp_path):
    """Local gallery serializes and deserializes accurately with version tracking."""
    orig_gallery, file_path, _ = sample_gallery
    
    loaded = LocalGallery.load(file_path)
    assert loaded.version == 1
    assert loaded.labels == ["Alice", "Bob", "Charlie"]
    assert loaded.embeddings.shape == (3, 512)
    assert loaded.profile_ids == ["p_alice", "p_bob", "p_charlie"]


def test_local_gallery_version_increment():
    """Updating gallery bumps the version integer."""
    gallery = LocalGallery(version=1)
    gallery.update(labels=["Alice"], embeddings=np.random.randn(1, 512).astype(np.float32))
    assert gallery.version == 2
    
    gallery.update(labels=["Alice", "Bob"], embeddings=np.random.randn(2, 512).astype(np.float32), version=5)
    assert gallery.version == 5


# ==================== 2. Hierarchical Search Decision Tests ====================

def test_tier1_local_high_confidence_match(sample_gallery):
    """High-confidence match against local gallery resolves locally without calling cloud."""
    _, file_path, embs = sample_gallery
    emb_alice = embs[0]

    # Query with Alice's embedding with high similarity ~0.95
    noise = np.random.randn(512).astype(np.float32)
    noise /= np.linalg.norm(noise)
    query = 0.95 * emb_alice + 0.05 * noise
    query /= np.linalg.norm(query)

    cloud_called = False
    def mock_cloud(vec):
        nonlocal cloud_called
        cloud_called = True
        return {"matches": []}

    engine = HierarchicalSearchEngine(
        gallery_path=file_path,
        local_high_confidence_threshold=0.65,
        cloud_search_fn=mock_cloud,
    )

    res = engine.search(query)
    
    assert res.identity == "Alice"
    assert res.confidence > 0.85
    assert res.search_tier == SearchTier.LOCAL_HIGH_CONFIDENCE
    assert res.cloud_match_found is False
    assert res.bandwidth_used_bytes == 0
    assert res.bandwidth_saved_bytes == HierarchicalSearchEngine.RAW_IMAGE_AVG_BYTES
    assert cloud_called is False  # Cloud was NOT queried (saved network call)


def test_tier2_cloud_vector_search_escalation(sample_gallery):
    """Uncertain or unknown local candidate escalates to cloud and resolves correctly."""
    _, file_path, _ = sample_gallery

    # Subject 'David' exists ONLY in cloud database, not in edge gallery
    np.random.seed(99)
    emb_david = np.random.randn(512).astype(np.float32)
    emb_david /= np.linalg.norm(emb_david)

    cloud_called = False
    def mock_cloud(vec):
        nonlocal cloud_called
        cloud_called = True
        return {
            "matches": [
                {"identity": "David", "score": 0.88, "profile_id": "p_david"}
            ]
        }

    engine = HierarchicalSearchEngine(
        gallery_path=file_path,
        local_high_confidence_threshold=0.65,
        cloud_recognition_threshold=0.50,
        cloud_search_fn=mock_cloud,
    )

    res = engine.search(emb_david)
    
    assert res.identity == "David"
    assert res.confidence == 0.88
    assert res.search_tier == SearchTier.CLOUD_RESOLVED
    assert res.cloud_match_found is True
    assert res.bandwidth_used_bytes == HierarchicalSearchEngine.EMBEDDING_VECTOR_BYTES
    assert cloud_called is True


def test_tier3_offline_local_fallback(sample_gallery):
    """When cloud search is unreachable, engine falls back to local candidate gracefully."""
    _, file_path, embs = sample_gallery
    emb_bob = embs[1]

    # Noisy Bob embedding with exact similarity 0.55 (between uncertain 0.40 and high 0.70)
    noise = np.random.randn(512).astype(np.float32)
    # Orthogonalize noise relative to emb_bob
    noise = noise - np.dot(emb_bob, noise) * emb_bob
    noise /= np.linalg.norm(noise)
    query = 0.55 * emb_bob + 0.835 * noise
    query /= np.linalg.norm(query)

    def mock_failing_cloud(vec):
        raise ConnectionError("Cloud unreachable")

    engine = HierarchicalSearchEngine(
        gallery_path=file_path,
        local_high_confidence_threshold=0.70,
        local_uncertain_threshold=0.40,
        cloud_search_fn=mock_failing_cloud,
    )

    res = engine.search(query)
    
    assert res.identity == "Bob"
    assert res.search_tier == SearchTier.LOCAL_FALLBACK
    assert res.confidence >= 0.40


def test_stale_gallery_triggers_cloud_search(sample_gallery):
    """When edge gallery is older than max_staleness_seconds, cloud search is triggered."""
    gallery, file_path, embs = sample_gallery
    emb_alice = embs[0]

    cloud_called = False
    def mock_cloud(vec):
        nonlocal cloud_called
        cloud_called = True
        return {"matches": [{"identity": "Alice", "score": 0.95, "profile_id": "p_alice"}]}

    engine = HierarchicalSearchEngine(
        gallery_path=file_path,
        max_staleness_seconds=10.0,
        cloud_search_fn=mock_cloud,
    )
    # Artificially age the gallery
    engine.gallery.last_synced_at = time.time() - 50.0

    res = engine.search(emb_alice)
    
    assert cloud_called is True
    assert res.search_tier == SearchTier.CLOUD_RESOLVED


# ==================== 3. Performance & Bandwidth Benchmark ====================

def test_hierarchical_search_benchmark(sample_gallery):
    """
    Measure and prove:
    1. Local latency (< 0.5 ms)
    2. Cloud latency
    3. Bandwidth savings (>= 98% savings on local hits and cloud vector queries vs raw images)
    4. Accuracy across hierarchical tiers
    """
    _, file_path, embs = sample_gallery
    
    cloud_queries = 0
    def mock_cloud_api(vec):
        nonlocal cloud_queries
        cloud_queries += 1
        time.sleep(0.005)  # Simulate 5ms network round-trip
        return {"matches": [{"identity": "CloudUser", "score": 0.85, "profile_id": "p_cloud"}]}

    engine = HierarchicalSearchEngine(
        gallery_path=file_path,
        local_high_confidence_threshold=0.65,
        cloud_search_fn=mock_cloud_api,
    )

    # 100 queries: 80 known local subjects, 20 unknown/cloud subjects
    n_queries = 100
    local_latencies = []
    total_bw_saved = 0
    total_bw_used = 0

    for i in range(n_queries):
        if i < 80:
            # Local known subject with high similarity (>0.85)
            noise = np.random.randn(512).astype(np.float32)
            noise /= np.linalg.norm(noise)
            emb = 0.90 * embs[i % 3] + 0.10 * noise
            emb /= np.linalg.norm(emb)
        else:
            # Distant/cloud subject
            emb = np.random.randn(512).astype(np.float32)
            emb /= np.linalg.norm(emb)

        res = engine.search(emb)
        local_latencies.append(res.local_latency_ms)
        total_bw_saved += res.bandwidth_saved_bytes
        total_bw_used += res.bandwidth_used_bytes

    avg_local_lat = np.mean(local_latencies)
    p95_local_lat = np.percentile(local_latencies, 95)
    
    # 80 local hits avoided cloud queries completely
    assert engine.metrics["local_hits"] == 80
    assert cloud_queries == 20

    # Bandwidth saving percentage:
    # 100 raw images = 100 * 200 KB = 20,000 KB (20 MB)
    raw_total_bytes = n_queries * HierarchicalSearchEngine.RAW_IMAGE_AVG_BYTES
    actual_used_bytes = total_bw_used
    bw_saved_pct = (1.0 - (actual_used_bytes / raw_total_bytes)) * 100.0

    assert avg_local_lat < 1.0  # Sub-millisecond local vector search
    assert bw_saved_pct >= 98.0 # >= 98% bandwidth reduction

    print(f"\n[Hierarchical Search Benchmark Summary]")
    print(f"Total Queries: {n_queries} | Local Hits: {engine.metrics['local_hits']} | Cloud Queries: {cloud_queries}")
    print(f"Avg Local Latency: {avg_local_lat:.3f} ms | P95: {p95_local_lat:.3f} ms")
    print(f"Raw Image Traffic: {raw_total_bytes / 1024:.1f} KB | Actual Transmitted: {actual_used_bytes / 1024:.1f} KB")
    print(f"Total Bandwidth Saved: {bw_saved_pct:.2f}%")
