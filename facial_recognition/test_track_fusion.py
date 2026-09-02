"""
Unit tests for Temporal Face-Track Identity Fusion.

Covers:
1. Stable identity accumulation and finalization
2. Resistance to noisy/poor-quality observations
3. Temporary occlusion recovery and track coasting
4. Conflicting embeddings and margin gating
5. Track disappearance, termination, and memory bounding
"""

import math
import time
import numpy as np
import pytest

from facial_recognition.track_fusion import (
    FaceObservation,
    FaceTrack,
    TemporalTrackManager,
    TrackStatus,
)


def make_unit_vector(seed: int) -> np.ndarray:
    """Generate a deterministic 512-d unit normalized embedding."""
    rng = np.random.RandomState(seed)
    vec = rng.randn(512).astype(np.float32)
    return vec / np.linalg.norm(vec)


@pytest.fixture
def gallery_data():
    """Create synthetic gallery with two distinct identities."""
    emb_alice = make_unit_vector(42)
    emb_bob = make_unit_vector(99)
    labels = ["Alice", "Bob"]
    embeddings = np.vstack([emb_alice, emb_bob])
    return labels, embeddings, emb_alice, emb_bob


@pytest.fixture
def track_manager():
    return TemporalTrackManager(
        max_observation_window_seconds=3.0,
        max_observations_per_track=20,
        min_observations_to_finalize=3,
        similarity_threshold=0.50,
        finalization_margin=0.08,
        max_missed_frames=5,
        quality_weight_gamma=2.0,
        temporal_decay_lambda=0.1,
        max_active_tracks=10,
        iou_association_threshold=0.20,
    )


def test_stable_identity_finalization(gallery_data, track_manager):
    """Test that consistent high-quality observations finalize to correct identity."""
    labels, embeddings, emb_alice, _ = gallery_data
    now = 1000.0

    # Feed 3 consistent high-quality observations of Alice
    for i in range(3):
        # Slightly noisy vector that still matches Alice strongly
        obs_emb = emb_alice + (np.random.RandomState(i).randn(512) * 0.05).astype(np.float32)
        obs_emb /= np.linalg.norm(obs_emb)

        obs = FaceObservation(
            timestamp=now + (i * 0.1),
            bbox=[100 + i, 100, 200 + i, 200],
            quality_score=95.0,
            quality_category="HIGH",
            confidence=0.95,
            embedding=obs_emb,
        )
        pairs = track_manager.process_frame_observations([obs], labels, embeddings, current_time=now + (i * 0.1))
        assert len(pairs) == 1
        track, _ = pairs[0]

    # After 3 high-quality observations, track should be FINALIZED as Alice
    assert track.is_finalized is True
    assert track.finalized_identity == "Alice"
    assert track.fused_confidence > 0.80
    assert track.top2_margin > 0.08
    assert track.status == TrackStatus.FINALIZED


def test_noisy_observations_cannot_override_strong(gallery_data):
    """Test that a single poor-quality frame cannot override strong observations."""
    labels, embeddings, emb_alice, emb_bob = gallery_data
    now = 1000.0

    # Initialize track with strong Alice observation
    initial_obs = FaceObservation(
        timestamp=now,
        bbox=[100, 100, 200, 200],
        quality_score=95.0, # High quality
        quality_category="HIGH",
        confidence=0.98,
        embedding=emb_alice,
    )
    track = FaceTrack(track_id=1, initial_observation=initial_obs, quality_weight_gamma=2.0)

    # Add second strong Alice observation
    track.add_observation(
        FaceObservation(
            timestamp=now + 0.1,
            bbox=[102, 100, 202, 200],
            quality_score=90.0,
            quality_category="HIGH",
            confidence=0.95,
            embedding=emb_alice,
        )
    )

    # Add 1 noisy/poor-quality observation pointing toward Bob (e.g. motion blur glitch)
    track.add_observation(
        FaceObservation(
            timestamp=now + 0.2,
            bbox=[104, 100, 204, 200],
            quality_score=25.0, # Low quality score
            quality_category="POOR",
            confidence=0.40,
            embedding=emb_bob,
        )
    )

    # Fuse identity
    ident, conf, finalized = track.fuse_identity(labels, embeddings, similarity_threshold=0.40)

    # Alice's high quality weights should dominate completely; fused identity remains Alice
    assert ident == "Alice"
    assert conf > 0.80
    assert track.fused_identity == "Alice"


def test_temporary_occlusion_and_coasting(gallery_data, track_manager):
    """Test that track enters COASTING during occlusion and resumes when face reappears."""
    labels, embeddings, emb_alice, _ = gallery_data
    t = 1000.0

    # 1. Initial observation
    obs1 = FaceObservation(
        timestamp=t,
        bbox=[100, 100, 200, 200],
        quality_score=90.0,
        quality_category="HIGH",
        confidence=0.95,
        embedding=emb_alice,
    )
    pairs = track_manager.process_frame_observations([obs1], labels, embeddings, current_time=t)
    track_id = pairs[0][0].track_id

    # 2. Simulate 3 frames of occlusion (empty detection list)
    for i in range(1, 4):
        t += 0.05
        pairs = track_manager.process_frame_observations([], labels, embeddings, current_time=t)
        assert len(pairs) == 0
        track = track_manager.get_track(track_id)
        assert track is not None
        assert track.status == TrackStatus.COASTING
        assert track.missed_frames == i

    # 3. Subject reappears within vicinity
    t += 0.05
    obs_reappear = FaceObservation(
        timestamp=t,
        bbox=[105, 102, 205, 202], # Overlapping bbox
        quality_score=92.0,
        quality_category="HIGH",
        confidence=0.96,
        embedding=emb_alice,
    )
    pairs = track_manager.process_frame_observations([obs_reappear], labels, embeddings, current_time=t)
    assert len(pairs) == 1
    reappeared_track, _ = pairs[0]

    # Track ID should be preserved
    assert reappeared_track.track_id == track_id
    assert reappeared_track.status in [TrackStatus.ACTIVE, TrackStatus.FINALIZED]
    assert reappeared_track.missed_frames == 0


def test_conflicting_embeddings_prevent_false_finalization(gallery_data, track_manager):
    """Test that tracks with conflicting identities fail the margin test and do not falsely finalize."""
    labels, embeddings, emb_alice, emb_bob = gallery_data
    t = 1000.0

    # Observation 1: Alice (weight 1.0)
    obs1 = FaceObservation(
        timestamp=t,
        bbox=[100, 100, 200, 200],
        quality_score=70.0,
        quality_category="MEDIUM",
        confidence=0.80,
        embedding=emb_alice,
    )
    # Observation 2: Bob (equal weight conflict)
    obs2 = FaceObservation(
        timestamp=t + 0.1,
        bbox=[102, 100, 202, 200],
        quality_score=70.0,
        quality_category="MEDIUM",
        confidence=0.80,
        embedding=emb_bob,
    )

    track_manager.process_frame_observations([obs1], labels, embeddings, current_time=t)
    pairs = track_manager.process_frame_observations([obs2], labels, embeddings, current_time=t + 0.1)
    track, _ = pairs[0]

    # With conflicting embeddings between Alice and Bob, top-2 margin is near 0
    assert track.top2_margin < track_manager.margin
    # Must NOT finalize because margin criteria is not met
    assert track.is_finalized is False


def test_track_termination_and_memory_bounding(gallery_data, track_manager):
    """Test that dead tracks terminate and memory is strictly bounded."""
    labels, embeddings, emb_alice, _ = gallery_data
    t = 1000.0

    # Create a track
    obs = FaceObservation(
        timestamp=t,
        bbox=[100, 100, 200, 200],
        quality_score=85.0,
        quality_category="HIGH",
        confidence=0.90,
        embedding=emb_alice,
    )
    pairs = track_manager.process_frame_observations([obs], labels, embeddings, current_time=t)
    track_id = pairs[0][0].track_id

    # Exceed max_missed_frames (5 frames)
    for _ in range(6):
        t += 0.1
        track_manager.process_frame_observations([], labels, embeddings, current_time=t)

    # Track should be purged / garbage collected
    assert track_manager.get_track(track_id) is None
    assert track_manager.active_tracks_count() == 0

    # Test max active tracks cap
    for i in range(25): # Create 25 disjoint tracks
        t += 0.01
        obs_i = FaceObservation(
            timestamp=t,
            bbox=[i * 20, i * 20, i * 20 + 10, i * 20 + 10], # Non-overlapping
            quality_score=80.0,
            quality_category="HIGH",
            confidence=0.85,
            embedding=emb_alice,
        )
        track_manager.process_frame_observations([obs_i], labels, embeddings, current_time=t)

    # Active tracks count should never exceed max_active_tracks (10)
    assert len(track_manager.tracks) <= track_manager.max_active_tracks
