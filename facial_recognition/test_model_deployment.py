"""
Tests for Safe Model Deployment, Pre-Activation Validation, Health Monitoring, and Atomic Rollback.

Covers:
1. Model Artifact Versioning and Metadata Manifest Creation
2. Pre-activation Validation (Checksum & Inference Smoke Testing)
3. Successful Deployment Lifecycle (Candidate -> Canary -> Active)
4. Failed Deployment (Smoke Test failure leaves active model intact)
5. Corrupted Artifact Rejection (Checksum mismatch)
6. Live Health Monitoring & Degradation Detection:
   - High Latency violation
   - Low FPS violation
   - Error Rate breach
   - Confidence Distribution Degradation
7. Automatic Atomic Rollback to Previous Known-Good Model
8. Process Restart Recovery during Mid-Deployment
9. Preservation of Previous Known-Good Model Artifacts on Disk
"""

import time
import pytest
import numpy as np
from pathlib import Path

from facial_recognition.model_deployment import (
    ModelDeploymentManager,
    ModelArtifactMetadata,
    ModelHealthPolicy,
    ModelHealthMonitor,
    ModelValidator,
    DeploymentState,
)


@pytest.fixture
def deployment_env(tmp_path):
    """Setup temporary deployment directory with initial v1 model."""
    base_dir = tmp_path / "edge_node"
    base_dir.mkdir(parents=True, exist_ok=True)

    policy = ModelHealthPolicy(
        max_avg_latency_ms=50.0,
        max_p95_latency_ms=100.0,
        min_fps=5.0,
        max_error_rate=0.10,
        min_avg_confidence=0.40,
        max_low_confidence_ratio=0.50,
        low_confidence_threshold=0.30,
        sliding_window_size=20,
        canary_window_seconds=0.1,  # Short for rapid test execution
    )

    manager = ModelDeploymentManager(base_dir=base_dir, health_policy=policy)
    
    # Register v1 model artifact
    dummy_v1_bytes = b"MODEL_WEIGHTS_V1_DUMMY_DATA"
    manager.register_model_artifact(
        version="v1",
        model_bytes=dummy_v1_bytes,
        input_shape=[1, 3, 112, 112],
        output_shape=[1, 512],
        description="Initial known-good v1 model",
    )
    manager.active_version = "v1"
    manager._save_state_atomic()

    return manager, base_dir


# ==================== 1. Pre-Activation & Deployment Lifecycle ====================

def test_successful_candidate_deployment(deployment_env):
    """Candidate model passes validation, activates in canary mode, and graduates to active."""
    manager, _ = deployment_env

    # Register candidate v2
    v2_bytes = b"MODEL_WEIGHTS_V2_ACCURATE"
    manager.register_model_artifact(
        version="v2",
        model_bytes=v2_bytes,
        input_shape=[1, 3, 112, 112],
        output_shape=[1, 512],
        description="Next-gen v2 candidate",
    )

    def healthy_infer(x):
        return np.ones((1, 512), dtype=np.float32)

    # Deploy candidate
    success, msg = manager.deploy_candidate("v2", infer_fn=healthy_infer)
    assert success is True
    assert manager.active_version == "v2"
    assert manager.previous_known_good_version == "v1"
    assert manager.deployment_state == DeploymentState.CANARY_ACTIVE

    # Simulate healthy canary observations
    time.sleep(0.15)
    for _ in range(10):
        manager.record_inference_observation(latency_ms=20.0, confidence=0.85)

    # Should graduate to ACTIVE
    assert manager.deployment_state == DeploymentState.ACTIVE
    assert manager.active_version == "v2"
    assert manager.previous_known_good_version == "v1"


def test_failed_deployment_leaves_active_model_intact(deployment_env):
    """Candidate failing smoke test (e.g. returns NaN) is rejected; active model remains v1."""
    manager, _ = deployment_env

    manager.register_model_artifact(
        version="v2_broken",
        model_bytes=b"MODEL_WEIGHTS_BROKEN",
        input_shape=[1, 3, 112, 112],
        output_shape=[1, 512],
    )

    def broken_infer(x):
        # Returns NaN values
        return np.array([[np.nan] * 512], dtype=np.float32)

    success, msg = manager.deploy_candidate("v2_broken", infer_fn=broken_infer)
    assert success is False
    assert "NaN or Inf" in msg
    assert manager.active_version == "v1"  # Still running known-good v1
    assert manager.deployment_state == DeploymentState.FAILED


def test_corrupted_model_artifact_checksum_rejection(deployment_env):
    """Candidate with modified/corrupted file bytes is rejected on checksum mismatch."""
    manager, base_dir = deployment_env

    manager.register_model_artifact(
        version="v2_tampered",
        model_bytes=b"ORIGINAL_BYTES",
        input_shape=[1, 3, 112, 112],
        output_shape=[1, 512],
    )

    # Corrupt model file on disk
    model_file = base_dir / "models" / "v2_tampered" / "model.bin"
    with open(model_file, "wb") as f:
        f.write(b"CORRUPTED_TAMPERED_BYTES")

    success, msg = manager.deploy_candidate("v2_tampered")
    assert success is False
    assert "Checksum mismatch" in msg
    assert manager.active_version == "v1"


# ==================== 2. Live Health Degradation & Rollback ====================

def test_automatic_rollback_on_high_latency_degradation(deployment_env):
    """Active candidate exhibiting severe latency degradation triggers automatic atomic rollback."""
    manager, _ = deployment_env

    manager.register_model_artifact(
        version="v2_slow",
        model_bytes=b"MODEL_SLOW",
        input_shape=[1, 3, 112, 112],
        output_shape=[1, 512],
    )
    manager.deploy_candidate("v2_slow", infer_fn=lambda x: np.ones((1, 512), dtype=np.float32))
    assert manager.active_version == "v2_slow"

    rollback_called = False
    def rollback_callback(failed, restored, reasons):
        nonlocal rollback_called
        rollback_called = True
        assert failed == "v2_slow"
        assert restored == "v1"

    manager.on_rollback_cb = rollback_callback

    # Inject high latency observations (> 50ms policy limit)
    for _ in range(8):
        manager.record_inference_observation(latency_ms=150.0, confidence=0.80)

    # Automatic rollback should have occurred
    assert manager.active_version == "v1"
    assert manager.deployment_state == DeploymentState.ROLLED_BACK
    assert rollback_called is True


def test_automatic_rollback_on_confidence_distribution_degradation(deployment_env):
    """Candidate producing anomalous low confidence distribution triggers rollback."""
    manager, _ = deployment_env

    manager.register_model_artifact(
        version="v2_poor_acc",
        model_bytes=b"MODEL_POOR",
        input_shape=[1, 3, 112, 112],
        output_shape=[1, 512],
    )
    manager.deploy_candidate("v2_poor_acc", infer_fn=lambda x: np.ones((1, 512), dtype=np.float32))

    # Inject 8 consecutive low-confidence observations (confidence = 0.15 < 0.30 threshold)
    for _ in range(8):
        manager.record_inference_observation(latency_ms=15.0, confidence=0.15)

    assert manager.active_version == "v1"
    assert manager.deployment_state == DeploymentState.ROLLED_BACK


def test_automatic_rollback_on_error_rate_breach(deployment_env):
    """Candidate throwing errors above max_error_rate (10%) triggers rollback."""
    manager, _ = deployment_env

    manager.register_model_artifact(
        version="v2_crashing",
        model_bytes=b"MODEL_CRASH",
        input_shape=[1, 3, 112, 112],
        output_shape=[1, 512],
    )
    manager.deploy_candidate("v2_crashing", infer_fn=lambda x: np.ones((1, 512), dtype=np.float32))

    # 6 errors out of 10 observations (60% error rate > 10% limit)
    for i in range(10):
        manager.record_inference_observation(latency_ms=20.0, confidence=0.70, is_error=(i % 2 == 0))

    assert manager.active_version == "v1"
    assert manager.deployment_state == DeploymentState.ROLLED_BACK


# ==================== 3. Crash Resilience & Artifact Preservation ====================

def test_process_restart_recovery_during_deployment(deployment_env):
    """If edge node crashes mid-validation, restart recovers to active known-good model."""
    manager, base_dir = deployment_env

    # Simulate mid-deployment state written before a sudden crash
    manager.candidate_version = "v2_unvalidated"
    manager.deployment_state = DeploymentState.VALIDATING_CANDIDATE
    manager._save_state_atomic()

    # Simulate node reboot: instantiate a fresh ModelDeploymentManager on the same directory
    restarted_manager = ModelDeploymentManager(base_dir=base_dir)

    assert restarted_manager.active_version == "v1"
    assert restarted_manager.candidate_version is None
    assert restarted_manager.deployment_state == DeploymentState.IDLE


def test_previous_known_good_model_preserved_on_disk(deployment_env):
    """Previous known-good model artifact files are never deleted and remain on disk."""
    manager, base_dir = deployment_env

    # Deploy v2
    manager.register_model_artifact("v2", b"MODEL_V2", [1, 3, 112, 112], [1, 512])
    manager.deploy_candidate("v2", infer_fn=lambda x: np.ones((1, 512), dtype=np.float32))

    # Deploy v3
    manager.register_model_artifact("v3", b"MODEL_V3", [1, 3, 112, 112], [1, 512])
    manager.deploy_candidate("v3", infer_fn=lambda x: np.ones((1, 512), dtype=np.float32))

    # Verify all 3 version artifacts remain on disk intact
    v1_file = base_dir / "models" / "v1" / "model.bin"
    v2_file = base_dir / "models" / "v2" / "model.bin"
    v3_file = base_dir / "models" / "v3" / "model.bin"

    assert v1_file.exists()
    assert v2_file.exists()
    assert v3_file.exists()
