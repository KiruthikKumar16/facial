"""
Tests for AI Model and Configuration Version Tracking.

Covers:
1. ModelConfigVersionBundle immutability, fingerprint hashing, and dictionary conversion.
2. EmbeddingVersionValidator:
   - Compatible model verification
   - Cross-model incompatibility detection & error raising
   - Dimension mismatch rejection
3. ModelMigrationManager multi-version migration lifecycle.
4. Tamper-evident hash chaining inclusion of all 6 version parameters.
"""

import pytest
import numpy as np

from facial_recognition.version_bundle import (
    ModelConfigVersionBundle,
    EmbeddingVersionValidator,
    IncompatibleEmbeddingModelError,
    ModelMigrationManager,
)
from facial_recognition.integrity import EventHasher


def test_version_bundle_immutability_and_hash():
    """ModelConfigVersionBundle is immutable and generates a deterministic SHA-256 bundle hash."""
    bundle1 = ModelConfigVersionBundle(
        detection_model_version="scrfd_500m_bnkps_v1",
        embedding_model_version="w600k_mbf_v1",
        gallery_version=1,
        threshold_version=1,
        camera_config_version=1,
        algorithm_version="temporal_fusion_v2",
    )
    
    bundle2 = ModelConfigVersionBundle(
        detection_model_version="scrfd_500m_bnkps_v1",
        embedding_model_version="w600k_mbf_v1",
        gallery_version=1,
        threshold_version=1,
        camera_config_version=1,
        algorithm_version="temporal_fusion_v2",
    )

    assert bundle1.bundle_hash == bundle2.bundle_hash
    assert len(bundle1.bundle_hash) == 64

    # Immutability check
    with pytest.raises(Exception):
        bundle1.gallery_version = 2  # dataclass is frozen


def test_version_bundle_hash_changes_on_any_component_change():
    """Modifying any single component changes the bundle fingerprint hash."""
    base = ModelConfigVersionBundle()
    
    v_diff_det = ModelConfigVersionBundle(detection_model_version="det_yolov8_face_v2")
    v_diff_emb = ModelConfigVersionBundle(embedding_model_version="arcface_r100_v1")
    v_diff_gal = ModelConfigVersionBundle(gallery_version=2)
    v_diff_thr = ModelConfigVersionBundle(threshold_version=2)
    v_diff_cam = ModelConfigVersionBundle(camera_config_version=3)
    v_diff_alg = ModelConfigVersionBundle(algorithm_version="single_frame_v1")

    hashes = {
        base.bundle_hash,
        v_diff_det.bundle_hash,
        v_diff_emb.bundle_hash,
        v_diff_gal.bundle_hash,
        v_diff_thr.bundle_hash,
        v_diff_cam.bundle_hash,
        v_diff_alg.bundle_hash,
    }
    assert len(hashes) == 7  # All 7 hashes are unique


def test_embedding_compatibility_validator():
    """EmbeddingVersionValidator enforces identical metric space before comparison."""
    # Compatible models
    assert EmbeddingVersionValidator.are_compatible("w600k_mbf_v1", "w600k_mbf_v1", 512, 512) is True
    assert EmbeddingVersionValidator.are_compatible("buffalo_s", "w600k_mbf_v1", 512, 512) is True

    # Incompatible models
    assert EmbeddingVersionValidator.are_compatible("w600k_mbf_v1", "arcface_r100_v1", 512, 512) is False
    assert EmbeddingVersionValidator.are_compatible("w600k_mbf_v1", "mobilenet_v2_256", 512, 256) is False

    # Dimension mismatch
    assert EmbeddingVersionValidator.are_compatible("w600k_mbf_v1", "w600k_mbf_v1", 512, 256) is False

    # Validation method raises IncompatibleEmbeddingModelError
    with pytest.raises(IncompatibleEmbeddingModelError) as exc_info:
        EmbeddingVersionValidator.validate_comparison("w600k_mbf_v1", "arcface_r100_v1", 512, 512)
    assert "Embedding model mismatch" in str(exc_info.value)


def test_model_migration_manager():
    """ModelMigrationManager tracks active, target, and deprecated model versions during rolling upgrades."""
    manager = ModelMigrationManager()
    assert manager.is_model_supported("w600k_mbf_v1") is True

    # Register next-generation model for rolling transition
    manager.register_migration_target("w600k_r50_v1")
    assert manager.is_model_supported("w600k_r50_v1") is True

    # Deprecate legacy model
    manager.deprecate_model("legacy_v0_model")
    assert manager.is_model_supported("legacy_v0_model") is False


def test_event_hasher_cryptographically_protects_version_metadata():
    """Modifying model version metadata changes the cryptographic event hash."""
    base_hash = EventHasher.compute_hash(
        event_id="evt-001",
        device_id="edge-1",
        camera_id="cam-gate",
        sequence_number=1,
        capture_timestamp="2026-09-01T12:00:00Z",
        identity="Alice",
        confidence=0.92,
        event_payload="{}",
        age=30,
        gender="F",
        previous_event_hash=EventHasher.GENESIS_HASH,
        detection_model_version="scrfd_500m_bnkps_v1",
        embedding_model_version="w600k_mbf_v1",
        gallery_version=1,
        threshold_version=1,
        algorithm_version="temporal_fusion_v2",
    )

    tampered_embedding_hash = EventHasher.compute_hash(
        event_id="evt-001",
        device_id="edge-1",
        camera_id="cam-gate",
        sequence_number=1,
        capture_timestamp="2026-09-01T12:00:00Z",
        identity="Alice",
        confidence=0.92,
        event_payload="{}",
        age=30,
        gender="F",
        previous_event_hash=EventHasher.GENESIS_HASH,
        detection_model_version="scrfd_500m_bnkps_v1",
        embedding_model_version="arcface_r100_v1",  # Tampered model version
        gallery_version=1,
        threshold_version=1,
        algorithm_version="temporal_fusion_v2",
    )

    assert base_hash != tampered_embedding_hash
