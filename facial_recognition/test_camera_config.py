"""
Tests for Per-Camera Adaptive Recognition Configuration.

Covers:
1. Camera A and B use completely different parameters
2. Default config is created on first access
3. Version increments on each update
4. Rollback creates a new version with old params
5. Config version is attached to recognition events
6. Offline caching - config is loaded from disk when backend is offline
7. Two distinct cameras maintain independent configurations
"""

import json
import time
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict

import pytest

from facial_recognition.camera_config import (
    CameraConfigProfile,
    CameraConfigManager,
)


# ==================== CameraConfigProfile Unit Tests ====================

def test_camera_config_profile_defaults():
    """Default profile has expected threshold values."""
    profile = CameraConfigProfile(camera_id="cam-a")
    assert profile.version == 1
    assert profile.detection_threshold == 0.50
    assert profile.recognition_threshold == 0.35
    assert profile.sampling_rate == 1
    assert profile.temporal_window == 3.0
    assert profile.quality_thresholds is None


def test_camera_config_profile_serialization_roundtrip():
    """Serialization and deserialization are lossless."""
    original = CameraConfigProfile(
        camera_id="cam-lobby",
        version=3,
        detection_threshold=0.65,
        recognition_threshold=0.55,
        quality_thresholds={"high": {"min_size": 64}},
        sampling_rate=2,
        temporal_window=5.0,
        notes="High-traffic lobby camera",
        updated_at=12345.0,
    )
    data = original.to_dict()
    restored = CameraConfigProfile.from_dict(data)

    assert restored.camera_id == original.camera_id
    assert restored.version == original.version
    assert restored.detection_threshold == original.detection_threshold
    assert restored.recognition_threshold == original.recognition_threshold
    assert restored.quality_thresholds == original.quality_thresholds
    assert restored.sampling_rate == original.sampling_rate
    assert restored.temporal_window == original.temporal_window
    assert restored.notes == original.notes


# ==================== CameraConfigManager Tests ====================

@pytest.fixture
def cache_dir(tmp_path):
    return str(tmp_path / "camera_configs_cache.json")


def test_get_profile_creates_default(cache_dir):
    """get_profile() creates and caches a default profile if camera is unknown."""
    manager = CameraConfigManager(
        cache_path=cache_dir,
        api_url="http://unreachable.invalid",
    )
    profile = manager.get_profile("cam-entrance")
    assert profile.camera_id == "cam-entrance"
    assert profile.version == 1
    # Profile should now be in the local cache file
    assert Path(cache_dir).exists()
    with open(cache_dir) as f:
        data = json.load(f)
    assert "cam-entrance" in data


def test_camera_a_and_b_have_different_params(cache_dir):
    """Camera A and Camera B can have independently distinct configurations."""
    manager = CameraConfigManager(
        cache_path=cache_dir,
        api_url="http://unreachable.invalid",
    )

    # Configure Camera A: bright outdoor lot, strict thresholds
    profile_a = CameraConfigProfile(
        camera_id="cam-a",
        version=1,
        detection_threshold=0.70,
        recognition_threshold=0.55,
        sampling_rate=1,
        temporal_window=2.0,
        notes="Outdoor lot — sharp faces, strict",
    )
    manager.update_profile(profile_a)

    # Configure Camera B: dim warehouse, lenient thresholds
    profile_b = CameraConfigProfile(
        camera_id="cam-b",
        version=1,
        detection_threshold=0.40,
        recognition_threshold=0.25,
        sampling_rate=4,
        temporal_window=6.0,
        notes="Dim warehouse — relaxed, high frame skip",
    )
    manager.update_profile(profile_b)

    fetched_a = manager.get_profile("cam-a")
    fetched_b = manager.get_profile("cam-b")

    assert fetched_a.detection_threshold == 0.70
    assert fetched_b.detection_threshold == 0.40
    assert fetched_a.recognition_threshold == 0.55
    assert fetched_b.recognition_threshold == 0.25
    assert fetched_a.sampling_rate == 1
    assert fetched_b.sampling_rate == 4
    assert fetched_a.temporal_window == 2.0
    assert fetched_b.temporal_window == 6.0
    # Confirm they do not share parameters
    assert fetched_a.detection_threshold != fetched_b.detection_threshold


def test_version_increments_on_update(cache_dir):
    """Storing a new profile with a higher version number is correctly persisted."""
    manager = CameraConfigManager(
        cache_path=cache_dir,
        api_url="http://unreachable.invalid",
    )

    v1 = CameraConfigProfile(camera_id="cam-x", version=1, recognition_threshold=0.40)
    manager.update_profile(v1)
    assert manager.get_profile("cam-x").version == 1

    v2 = CameraConfigProfile(camera_id="cam-x", version=2, recognition_threshold=0.50)
    manager.update_profile(v2)
    assert manager.get_profile("cam-x").version == 2
    assert manager.get_profile("cam-x").recognition_threshold == 0.50


def test_rollback_restores_previous_params(cache_dir):
    """After updating, storing a rollback profile restores old thresholds."""
    manager = CameraConfigManager(
        cache_path=cache_dir,
        api_url="http://unreachable.invalid",
    )

    v1 = CameraConfigProfile(camera_id="cam-y", version=1, recognition_threshold=0.35)
    manager.update_profile(v1)

    v2 = CameraConfigProfile(camera_id="cam-y", version=2, recognition_threshold=0.55)
    manager.update_profile(v2)

    # Rollback: new version with v1 params
    rollback = CameraConfigProfile(
        camera_id="cam-y",
        version=3,
        recognition_threshold=0.35,  # restored from v1
        notes="Rollback to v1 params",
    )
    manager.update_profile(rollback)

    current = manager.get_profile("cam-y")
    assert current.version == 3
    assert current.recognition_threshold == 0.35
    assert "Rollback" in (current.notes or "")


def test_offline_cache_persistence(tmp_path):
    """Edge node continues operating from disk cache when backend is unreachable."""
    cache_file = str(tmp_path / "configs.json")

    # Step 1: Write profiles to cache as if they had previously synced
    profiles = {
        "cam-offline-a": CameraConfigProfile(
            camera_id="cam-offline-a",
            version=5,
            detection_threshold=0.65,
            recognition_threshold=0.50,
        ).to_dict(),
        "cam-offline-b": CameraConfigProfile(
            camera_id="cam-offline-b",
            version=2,
            detection_threshold=0.35,
            recognition_threshold=0.20,
        ).to_dict(),
    }
    with open(cache_file, "w") as f:
        json.dump(profiles, f)

    # Step 2: Create manager pointing at unreachable backend
    manager = CameraConfigManager(
        cache_path=cache_file,
        api_url="http://unreachable.invalid:99999",
    )

    # Step 3: Verify cached profiles are loaded correctly without network
    pa = manager.get_profile("cam-offline-a")
    pb = manager.get_profile("cam-offline-b")

    assert pa.version == 5
    assert pa.detection_threshold == 0.65
    assert pb.version == 2
    assert pb.detection_threshold == 0.35


def test_config_version_attaches_to_ledger_event(tmp_path):
    """Recognition events store the config_version of the active camera profile."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from facial_recognition.event_ledger import EventLedger

    db_path = str(tmp_path / "test.db")
    ledger = EventLedger(db_path=db_path, device_id="test-device")

    # Add event with config_version=3
    event_id = ledger.add_event(
        camera_id="cam-versioned",
        identity="Alice",
        confidence=0.90,
        config_version=3,
    )

    # Verify config_version stored correctly
    conn = ledger._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config_version FROM recognition_events WHERE event_id = ?", (event_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row["config_version"] == 3

    ledger.close()


def test_config_version_is_part_of_tamper_evident_hash(tmp_path):
    """Changing config_version invalidates the ledger integrity check."""
    from facial_recognition.event_ledger import EventLedger

    db_path = str(tmp_path / "test_integrity.db")
    ledger = EventLedger(db_path=db_path, device_id="test-device")

    # Add a clean event with config_version=1
    ledger.add_event(
        camera_id="cam-integrity",
        identity="Bob",
        confidence=0.85,
        config_version=1,
    )

    # Verify chain is clean before tampering
    result = ledger.verify_ledger_integrity("cam-integrity")
    assert result["is_valid"] is True
    assert result["events_verified"] == 1

    # Tamper: silently change config_version in the DB via ledger's own connection
    conn = ledger._get_connection()
    conn.execute("UPDATE recognition_events SET config_version = 99 WHERE camera_id = 'cam-integrity'")
    conn.commit()

    # Force a clean read by closing and reopening the ledger
    ledger.close()

    ledger2 = EventLedger(db_path=db_path, device_id="test-device")
    tampered = ledger2.verify_ledger_integrity("cam-integrity")
    assert tampered["is_valid"] is False
    assert tampered["events_verified"] == 0
    ledger2.close()


def test_distinct_cameras_independent_config_versions(cache_dir):
    """Updating one camera's config does not affect any other camera's config."""
    manager = CameraConfigManager(
        cache_path=cache_dir,
        api_url="http://unreachable.invalid",
    )

    manager.update_profile(CameraConfigProfile(camera_id="cam-1", version=1, recognition_threshold=0.40))
    manager.update_profile(CameraConfigProfile(camera_id="cam-2", version=1, recognition_threshold=0.40))

    # Update only cam-1 to v2
    manager.update_profile(CameraConfigProfile(camera_id="cam-1", version=2, recognition_threshold=0.60))

    assert manager.get_profile("cam-1").version == 2
    assert manager.get_profile("cam-1").recognition_threshold == 0.60
    # cam-2 is completely unaffected
    assert manager.get_profile("cam-2").version == 1
    assert manager.get_profile("cam-2").recognition_threshold == 0.40
