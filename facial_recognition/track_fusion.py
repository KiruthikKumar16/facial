"""
Temporal Face-Track Identity Fusion Engine.

Maintains temporal face tracks with quality-weighted feature aggregation,
top-1 vs top-2 margin confidence testing, temporal decay, and track lifecycle management.
"""

from __future__ import annotations
import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class TrackStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FINALIZED = "FINALIZED"
    COASTING = "COASTING"
    TERMINATED = "TERMINATED"


@dataclass
class FaceObservation:
    """A single spatial-temporal observation of a face in a video frame."""
    timestamp: float
    bbox: List[int] # [x0, y0, x1, y2]
    quality_score: float # 0.0 - 100.0
    quality_category: str # "HIGH", "MEDIUM", "POOR"
    confidence: float # detector confidence score 0.0 - 1.0
    embedding: Optional[np.ndarray] = None # 512-d normalized embedding (None if POOR quality)
    track_id: Optional[int] = None


class FaceTrack:
    """
    A temporal face track aggregating observations of a single subject across time.
    Uses quality-weighted spherical vector fusion to produce stable identities.
    """
    def __init__(
        self,
        track_id: int,
        initial_observation: FaceObservation,
        max_observations: int = 30,
        observation_window_seconds: float = 3.0,
        quality_weight_gamma: float = 2.0,
        temporal_decay_lambda: float = 0.1,
    ):
        self.track_id = track_id
        self.max_observations = max_observations
        self.observation_window_seconds = observation_window_seconds
        self.gamma = quality_weight_gamma
        self.decay_lambda = temporal_decay_lambda

        self.created_at = initial_observation.timestamp
        self.last_updated = initial_observation.timestamp
        self.missed_frames = 0
        self.status = TrackStatus.ACTIVE

        # Bounded temporal observation deque
        self.observations: deque[FaceObservation] = deque(maxlen=max_observations)
        
        # Identity and fusion state
        self.fused_embedding: Optional[np.ndarray] = None
        self.fused_identity: str = "Unknown"
        self.fused_confidence: float = 0.0
        self.top2_margin: float = 0.0
        self.is_finalized: bool = False
        self.finalized_identity: Optional[str] = None
        self.finalized_at: Optional[float] = None

        # Add first observation
        self.add_observation(initial_observation)

    @property
    def latest_bbox(self) -> List[int]:
        if self.observations:
            return self.observations[-1].bbox
        return [0, 0, 0, 0]

    @property
    def valid_embeddings_count(self) -> int:
        return sum(1 for obs in self.observations if obs.embedding is not None)

    def add_observation(self, observation: FaceObservation) -> None:
        """Add a new observation to the track and purge expired observations."""
        observation.track_id = self.track_id
        self.observations.append(observation)
        self.last_updated = observation.timestamp
        self.missed_frames = 0
        if self.status == TrackStatus.COASTING:
            self.status = TrackStatus.FINALIZED if self.is_finalized else TrackStatus.ACTIVE

        self._purge_expired(observation.timestamp)

    def _purge_expired(self, current_time: float) -> None:
        """Evict observations older than the observation window."""
        cutoff = current_time - self.observation_window_seconds
        while self.observations and self.observations[0].timestamp < cutoff:
            self.observations.popleft()

    def update_missed_frame(self, max_missed: int = 15) -> None:
        """Update track state when no matching detection is found in a frame."""
        self.missed_frames += 1
        if self.missed_frames >= max_missed:
            self.status = TrackStatus.TERMINATED
        elif self.status != TrackStatus.TERMINATED:
            self.status = TrackStatus.COASTING

    def compute_fused_embedding(self, current_time: Optional[float] = None) -> Optional[np.ndarray]:
        """
        Compute the quality-weighted spherical Fréchet mean of observation embeddings:
        w_i = (quality / 100)^gamma * confidence * exp(-lambda * dt)
        e_fused = sum(w_i * e_i) / ||sum(w_i * e_i)||
        """
        if not self.observations:
            return None

        now = current_time if current_time is not None else self.last_updated
        weighted_sum = np.zeros(512, dtype=np.float64)
        total_weight = 0.0

        for obs in self.observations:
            if obs.embedding is None:
                continue

            dt = max(0.0, now - obs.timestamp)
            time_weight = math.exp(-self.decay_lambda * dt)
            
            # Non-linear quality weighting exponentially favors high-quality observations
            norm_q = max(0.0, min(1.0, obs.quality_score / 100.0))
            quality_weight = math.pow(norm_q, self.gamma)
            
            w = quality_weight * obs.confidence * time_weight
            if w > 1e-6:
                weighted_sum += w * obs.embedding.astype(np.float64)
                total_weight += w

        if total_weight < 1e-6:
            return None

        norm = np.linalg.norm(weighted_sum)
        if norm < 1e-10:
            return None

        self.fused_embedding = (weighted_sum / norm).astype(np.float32)
        return self.fused_embedding

    def fuse_identity(
        self,
        gallery_labels: List[str],
        gallery_embeddings: np.ndarray,
        similarity_threshold: float = 0.35,
        finalization_margin: float = 0.05,
        min_observations_to_finalize: int = 3,
        current_time: Optional[float] = None,
    ) -> Tuple[str, float, bool]:
        """
        Perform gallery matching using the fused embedding representation.
        Evaluates margin separation and finalization criteria.
        """
        if self.is_finalized and self.finalized_identity is not None:
            return self.finalized_identity, self.fused_confidence, True

        fused_emb = self.compute_fused_embedding(current_time)
        if fused_emb is None or gallery_embeddings.shape[0] == 0 or len(gallery_labels) == 0:
            self.fused_identity = "Unknown"
            self.fused_confidence = 0.0
            self.top2_margin = 0.0
            return "Unknown", 0.0, False

        # Compute cosine similarity across all gallery identities
        sims = np.dot(gallery_embeddings, fused_emb) / (
            np.linalg.norm(gallery_embeddings, axis=1) * np.linalg.norm(fused_emb) + 1e-10
        )

        top_indices = np.argsort(sims)[::-1]
        best_idx = int(top_indices[0])
        best_score = float(sims[best_idx])

        # Compute margin to second best distinct identity
        best_label = gallery_labels[best_idx]
        second_score = 0.0
        for idx in top_indices[1:]:
            if gallery_labels[idx] != best_label:
                second_score = float(sims[idx])
                break

        margin = max(0.0, best_score - second_score)
        self.top2_margin = margin
        self.fused_confidence = best_score

        if best_score >= similarity_threshold:
            self.fused_identity = best_label
        else:
            self.fused_identity = "Unknown"

        # Finalization criteria check:
        # 1. Minimum number of quality observations with embeddings
        # 2. Similarity meets or exceeds threshold
        # 3. Top-1 vs Top-2 margin separation is sufficient (or gallery has single subject)
        num_distinct = len(set(gallery_labels))
        margin_satisfied = (margin >= finalization_margin) if num_distinct > 1 else True

        if (
            self.valid_embeddings_count >= min_observations_to_finalize
            and best_score >= similarity_threshold
            and margin_satisfied
            and self.fused_identity != "Unknown"
        ):
            self.is_finalized = True
            self.finalized_identity = self.fused_identity
            self.finalized_at = current_time or self.last_updated
            self.status = TrackStatus.FINALIZED

        return self.fused_identity, self.fused_confidence, self.is_finalized


class TemporalTrackManager:
    """
    Manages active face tracks, spatial-temporal association, identity fusion,
    and garbage collection of terminated tracks.
    """
    def __init__(
        self,
        max_observation_window_seconds: float = 3.0,
        max_observations_per_track: int = 30,
        min_observations_to_finalize: int = 3,
        similarity_threshold: float = 0.35,
        finalization_margin: float = 0.05,
        max_missed_frames: int = 15,
        quality_weight_gamma: float = 2.0,
        temporal_decay_lambda: float = 0.1,
        max_active_tracks: int = 50,
        iou_association_threshold: float = 0.25,
    ):
        self.window_sec = max_observation_window_seconds
        self.max_obs = max_observations_per_track
        self.min_obs = min_observations_to_finalize
        self.sim_thresh = similarity_threshold
        self.margin = finalization_margin
        self.max_missed = max_missed_frames
        self.gamma = quality_weight_gamma
        self.decay_lambda = temporal_decay_lambda
        self.max_active_tracks = max_active_tracks
        self.iou_thresh = iou_association_threshold

        self.tracks: Dict[int, FaceTrack] = {}
        self._next_track_id: int = 1

    @staticmethod
    def compute_iou(boxA: List[int], boxB: List[int]) -> float:
        """Calculate Intersection over Union between two bounding boxes."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        inter_w = max(0, xB - xA)
        inter_h = max(0, yB - yA)
        inter_area = inter_w * inter_h

        boxAArea = max(1, (boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
        boxBArea = max(1, (boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))
        
        iou = inter_area / float(boxAArea + boxBArea - inter_area + 1e-6)
        return float(iou)

    def process_frame_observations(
        self,
        observations: List[FaceObservation],
        gallery_labels: List[str],
        gallery_embeddings: np.ndarray,
        current_time: Optional[float] = None,
    ) -> List[Tuple[FaceTrack, FaceObservation]]:
        """
        Associate frame detections with existing face tracks, update observations,
        fuse identities, and return paired (track, observation) results.
        """
        now = current_time if current_time is not None else time.time()
        active_track_ids = [tid for tid, t in self.tracks.items() if t.status != TrackStatus.TERMINATED]

        # Cost matrix based on IoU
        matched_tracks = set()
        matched_obs = set()
        pairs: List[Tuple[FaceTrack, FaceObservation]] = []

        if active_track_ids and observations:
            # Build IoU matches
            match_candidates: List[Tuple[float, int, int]] = []
            for obs_idx, obs in enumerate(observations):
                for tid in active_track_ids:
                    track = self.tracks[tid]
                    iou = self.compute_iou(obs.bbox, track.latest_bbox)
                    if iou >= self.iou_thresh:
                        match_candidates.append((iou, obs_idx, tid))

            # Sort by highest IoU
            match_candidates.sort(key=lambda x: x[0], reverse=True)
            for iou, obs_idx, tid in match_candidates:
                if obs_idx not in matched_obs and tid not in matched_tracks:
                    matched_obs.add(obs_idx)
                    matched_tracks.add(tid)
                    track = self.tracks[tid]
                    obs = observations[obs_idx]
                    track.add_observation(obs)
                    pairs.append((track, obs))

        # Handle unmatched observations -> create new tracks
        for obs_idx, obs in enumerate(observations):
            if obs_idx not in matched_obs:
                track_id = self._next_track_id
                self._next_track_id += 1
                new_track = FaceTrack(
                    track_id=track_id,
                    initial_observation=obs,
                    max_observations=self.max_obs,
                    observation_window_seconds=self.window_sec,
                    quality_weight_gamma=self.gamma,
                    temporal_decay_lambda=self.decay_lambda,
                )
                self.tracks[track_id] = new_track
                pairs.append((new_track, obs))

        # Handle unmatched active tracks -> increment missed frames
        for tid in active_track_ids:
            if tid not in matched_tracks:
                track = self.tracks[tid]
                track.update_missed_frame(self.max_missed)

        # Fuse identities for all updated tracks
        for track, _ in pairs:
            track.fuse_identity(
                gallery_labels=gallery_labels,
                gallery_embeddings=gallery_embeddings,
                similarity_threshold=self.sim_thresh,
                finalization_margin=self.margin,
                min_observations_to_finalize=self.min_obs,
                current_time=now,
            )

        # Garbage collect terminated tracks and bound memory
        self._prune_tracks()

        return pairs

    def _prune_tracks(self) -> None:
        """Remove terminated tracks and ensure active tracks do not exceed memory cap."""
        # 1. Remove TERMINATED tracks
        to_delete = [tid for tid, track in self.tracks.items() if track.status == TrackStatus.TERMINATED]
        for tid in to_delete:
            del self.tracks[tid]

        # 2. If track count exceeds max_active_tracks, prune oldest coasting/terminated tracks
        if len(self.tracks) > self.max_active_tracks:
            sorted_tracks = sorted(self.tracks.items(), key=lambda item: item[1].last_updated)
            excess = len(self.tracks) - self.max_active_tracks
            for i in range(excess):
                del self.tracks[sorted_tracks[i][0]]

    def get_track(self, track_id: int) -> Optional[FaceTrack]:
        return self.tracks.get(track_id)

    def active_tracks_count(self) -> int:
        return sum(1 for t in self.tracks.values() if t.status != TrackStatus.TERMINATED)
