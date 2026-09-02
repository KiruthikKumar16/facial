"""
Tests for Recognition Provenance Tracking.

Covers:
1. ProvenanceTracker building 7-stage lineage graph
2. Cryptographic immutability via provenance_chain_hash
3. Non-exposure of raw biometric vectors (SHA-256 fingerprint verification)
4. Temporal track and candidate evaluation references
"""

import hashlib
import numpy as np
import pytest

from facial_recognition.provenance import (
    CandidateSummary,
    ProcessingStage,
    ProvenanceTracker,
    RecognitionProvenance,
)


def test_provenance_builder_full_lineage():
    """Builds a complete 7-stage recognition lineage graph."""
    tracker = ProvenanceTracker(
        camera_id="cam-lobby-01",
        frame_reference="frame_cam-lobby-01_1720000000000_12",
        track_id="track_cam-lobby-01_042",
    )
    tracker.add_observation("obs_001")
    tracker.add_observation("obs_002")
    tracker.add_observation("obs_003")

    tracker.set_models(
        detection_model="scrfd_500m_bnkps_v1",
        embedding_model="w600k_mbf_v1",
    )

    # Set mock 512-d embedding
    dummy_embedding = np.random.randn(512).astype(np.float32)
    tracker.set_embedding_vector(dummy_embedding)

    tracker.add_candidate(identity="Alice Smith", score=0.945, profile_id="prof-alice-01", rank=1)
    tracker.add_candidate(identity="Bob Jones", score=0.421, profile_id="prof-bob-02", rank=2)

    prov = tracker.finalize(
        event_id="evt-prov-1001",
        identity="Alice Smith",
        confidence=0.945,
        decision_tier="LOCAL_HIGH_CONFIDENCE",
    )

    assert prov.event_id == "evt-prov-1001"
    assert prov.camera_id == "cam-lobby-01"
    assert prov.frame_reference == "frame_cam-lobby-01_1720000000000_12"
    assert prov.track_id == "track_cam-lobby-01_042"
    assert len(prov.observation_references) == 3
    assert len(prov.candidate_matches) == 2
    assert prov.selected_identity == "Alice Smith"
    assert prov.confidence == 0.945

    # Verify 7 distinct stages generated
    stages = prov.get_lineage_stages()
    assert len(stages) == 7
    stage_names = [s.stage_name for s in stages]
    assert "1. Camera Ingestion" in stage_names[0]
    assert "2. Frame Acquisition" in stage_names[1]
    assert "3. Face Tracking" in stage_names[2]
    assert "4. Embedding Feature Extraction" in stage_names[3]
    assert "5. Candidate Evaluation" in stage_names[4]
    assert "6. Recognition Decision" in stage_names[5]
    assert "7. Cloud Synchronization" in stage_names[6]


def test_provenance_chain_hash_is_deterministic_and_tamper_evident():
    """Cryptographic chain hash changes if any lineage parameter is modified."""
    prov = RecognitionProvenance(
        event_id="evt-prov-hash-1",
        camera_id="cam-01",
        frame_reference="frame-01",
        track_id="track-01",
        observation_references=["obs-1"],
        detection_model_version="scrfd_v1",
        embedding_model_version="mbf_v1",
        embedding_fingerprint="abc123hash",
        candidate_matches=[CandidateSummary(identity="Charlie", score=0.91)],
        decision_tier="LOCAL_HIGH_CONFIDENCE",
        selected_identity="Charlie",
        confidence=0.91,
        decision_timestamp=1700000000.0,
    )
    hash_original = prov.provenance_chain_hash
    assert isinstance(hash_original, str)
    assert len(hash_original) == 64

    # Tampering with confidence changes the hash
    prov_tampered = RecognitionProvenance(
        event_id="evt-prov-hash-1",
        camera_id="cam-01",
        frame_reference="frame-01",
        track_id="track-01",
        observation_references=["obs-1"],
        detection_model_version="scrfd_v1",
        embedding_model_version="mbf_v1",
        embedding_fingerprint="abc123hash",
        candidate_matches=[CandidateSummary(identity="Charlie", score=0.91)],
        decision_tier="LOCAL_HIGH_CONFIDENCE",
        selected_identity="Charlie",
        confidence=0.99,  # Changed!
        decision_timestamp=1700000000.0,
    )
    assert prov_tampered.provenance_chain_hash != hash_original


def test_biometric_privacy_protection():
    """Raw 512-float vector is never serialized in provenance dictionary; only SHA-256 fingerprint."""
    tracker = ProvenanceTracker(camera_id="cam-priv")
    emb = np.ones(512, dtype=np.float32)
    tracker.set_embedding_vector(emb)
    prov = tracker.finalize(event_id="evt-priv-1", identity="Test", confidence=0.85)

    prov_dict = prov.to_dict()
    # Check that raw 512-d list is NOT present
    assert "embedding_vector" not in prov_dict
    assert "embedding" not in prov_dict
    # Fingerprint is present
    assert "embedding_fingerprint" in prov_dict
    assert len(prov_dict["embedding_fingerprint"]) == 64
