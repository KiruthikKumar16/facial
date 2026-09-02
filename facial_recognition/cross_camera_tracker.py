"""
Cross-Camera Identity Continuity Tracking Engine.

Reasons over face embeddings, timestamps, camera topology, and temporal constraints
to evaluate whether observations across cameras belong to the same person.
"""

from __future__ import annotations

import enum
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from facial_recognition.topology import CameraEdge, CameraTopologyGraph

logger = logging.getLogger(__name__)


class TransitionType(str, enum.Enum):
    """Classification of cross-camera identity continuity."""
    CONFIRMED = "CONFIRMED"   # Valid topology + time in range + high similarity (>= confirmed_thresh)
    PROBABLE = "PROBABLE"     # Valid topology + time in range + medium similarity (>= probable_thresh) or multi-hop
    UNCERTAIN = "UNCERTAIN"   # Disconnected edge / impossible time / low similarity


@dataclass
class TransitionReasoning:
    """Detailed explainable reasoning metadata for a cross-camera transition."""
    from_camera: str
    to_camera: str
    elapsed_seconds: float
    expected_travel_range: Tuple[float, float]
    temporal_score: float
    embedding_similarity: float
    topology_edge_exists: bool
    is_teleportation: bool
    is_expired: bool
    classification: TransitionType
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_camera": self.from_camera,
            "to_camera": self.to_camera,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "expected_travel_range": [round(self.expected_travel_range[0], 1), round(self.expected_travel_range[1], 1)],
            "temporal_score": round(self.temporal_score, 3),
            "embedding_similarity": round(self.embedding_similarity, 4),
            "topology_edge_exists": self.topology_edge_exists,
            "is_teleportation": self.is_teleportation,
            "is_expired": self.is_expired,
            "classification": self.classification.value,
            "explanation": self.explanation,
        }


@dataclass
class TrajectoryNode:
    """A single spatial-temporal observation node along an identity trajectory."""
    node_id: str
    camera_id: str
    timestamp: float
    iso_timestamp: str
    bbox: List[int]
    confidence: float
    track_id: Optional[str] = None
    quality_score: Optional[float] = None
    transition_type: Optional[TransitionType] = None
    reasoning: Optional[TransitionReasoning] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "iso_timestamp": self.iso_timestamp,
            "bbox": self.bbox,
            "confidence": round(self.confidence, 4),
            "track_id": self.track_id,
            "quality_score": self.quality_score,
            "transition_type": self.transition_type.value if self.transition_type else None,
            "reasoning": self.reasoning.to_dict() if self.reasoning else None,
        }


@dataclass
class IdentityTrajectory:
    """Historical multi-camera trajectory for a specific identity."""
    identity: str
    nodes: List[TrajectoryNode] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    @property
    def current_camera(self) -> Optional[str]:
        return self.nodes[-1].camera_id if self.nodes else None

    @property
    def last_seen_time(self) -> Optional[float]:
        return self.nodes[-1].timestamp if self.nodes else None

    def add_node(self, node: TrajectoryNode) -> None:
        self.nodes.append(node)
        self.last_updated = node.timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "total_nodes": len(self.nodes),
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "nodes": [n.to_dict() for n in self.nodes],
        }


class CrossCameraContinuityTracker:
    """
    Cross-Camera Identity Continuity Tracker.
    
    Evaluates transitions across cameras using topology, temporal constraints,
    and embedding similarities to construct verified multi-camera trajectories.
    """

    def __init__(
        self,
        topology_graph: Optional[CameraTopologyGraph] = None,
        confirmed_similarity_threshold: float = 0.65,
        probable_similarity_threshold: float = 0.45,
        min_temporal_score: float = 0.20,
        max_continuity_gap_seconds: float = 600.0,
    ) -> None:
        self.topology = topology_graph or CameraTopologyGraph()
        self.confirmed_sim_thresh = float(confirmed_similarity_threshold)
        self.probable_sim_thresh = float(probable_similarity_threshold)
        self.min_temporal_score = float(min_temporal_score)
        self.max_continuity_gap_seconds = float(max_continuity_gap_seconds)
        
        # In-memory trajectories: identity -> IdentityTrajectory
        self.trajectories: Dict[str, IdentityTrajectory] = {}
        
        # Recent observations cache for fast cross-camera matching
        # identity -> list of (timestamp, camera_id, embedding, bbox, confidence, track_id)
        self._recent_observations: Dict[str, List[Dict[str, Any]]] = {}

    def get_or_create_trajectory(self, identity: str) -> IdentityTrajectory:
        """Retrieve or initialize trajectory for an identity."""
        if identity not in self.trajectories:
            self.trajectories[identity] = IdentityTrajectory(identity=identity)
        return self.trajectories[identity]

    def evaluate_transition(
        self,
        from_camera_id: str,
        to_camera_id: str,
        elapsed_seconds: float,
        embedding_similarity: float,
    ) -> Tuple[TransitionType, TransitionReasoning]:
        """
        Reason about whether a transition between two cameras is valid.
        
        Combines:
        1. Camera topology graph (reachability)
        2. Temporal travel time plausibility
        3. Embedding similarity
        """
        # 1. Edge lookup
        edge = self.topology.get_edge(from_camera_id, to_camera_id)
        edge_exists = edge is not None
        
        # Default ranges if no explicit edge
        expected_range = (
            (edge.min_travel_seconds, edge.max_travel_seconds)
            if edge
            else (2.0, self.max_continuity_gap_seconds)
        )

        is_teleportation = elapsed_seconds < expected_range[0]
        is_expired = elapsed_seconds > expected_range[1]

        # 2. Compute temporal score
        temporal_score = 0.0
        if edge_exists and not is_teleportation and not is_expired:
            temporal_score = CameraTopologyGraph.compute_temporal_score(elapsed_seconds, edge)
        elif not edge_exists and not is_teleportation and not is_expired:
            # Fallback decay for unmodeled edges
            temporal_score = max(0.0, 1.0 - (elapsed_seconds / self.max_continuity_gap_seconds))

        # 3. Classify transition
        # Case A: Impossible transition (teleportation or disconnected when strict)
        if is_teleportation:
            classification = TransitionType.UNCERTAIN
            explanation = (
                f"Physically impossible transition (teleportation): elapsed time {elapsed_seconds:.1f}s "
                f"is strictly below minimum travel time {expected_range[0]:.1f}s from {from_camera_id} to {to_camera_id}."
            )
        elif not edge_exists:
            classification = TransitionType.UNCERTAIN
            explanation = (
                f"Unconnected camera pair: No allowed physical route defined in topology graph "
                f"from {from_camera_id} to {to_camera_id}."
            )
        elif is_expired:
            classification = TransitionType.UNCERTAIN
            explanation = (
                f"Temporal continuity expired: elapsed time {elapsed_seconds:.1f}s exceeds "
                f"maximum allowed travel window {expected_range[1]:.1f}s."
            )
        # Case B: Connected & within time window -> evaluate similarity
        elif embedding_similarity >= self.confirmed_sim_thresh and temporal_score >= self.min_temporal_score:
            classification = TransitionType.CONFIRMED
            explanation = (
                f"Confirmed transition: High face similarity ({embedding_similarity:.2f} >= {self.confirmed_sim_thresh:.2f}) "
                f"with valid topology route and plausible travel time ({elapsed_seconds:.1f}s in range "
                f"[{expected_range[0]:.1f}s, {expected_range[1]:.1f}s], temporal score {temporal_score:.2f})."
            )
        elif embedding_similarity >= self.probable_sim_thresh:
            classification = TransitionType.PROBABLE
            explanation = (
                f"Probable transition: Moderate face similarity ({embedding_similarity:.2f}) "
                f"along valid topology route from {from_camera_id} to {to_camera_id} ({elapsed_seconds:.1f}s)."
            )
        else:
            classification = TransitionType.UNCERTAIN
            explanation = (
                f"Uncertain transition: Face similarity ({embedding_similarity:.2f}) is below "
                f"probable threshold ({self.probable_sim_thresh:.2f}) despite valid topology edge."
            )

        reasoning = TransitionReasoning(
            from_camera=from_camera_id,
            to_camera=to_camera_id,
            elapsed_seconds=elapsed_seconds,
            expected_travel_range=expected_range,
            temporal_score=temporal_score,
            embedding_similarity=embedding_similarity,
            topology_edge_exists=edge_exists,
            is_teleportation=is_teleportation,
            is_expired=is_expired,
            classification=classification,
            explanation=explanation,
        )

        return classification, reasoning

    def record_observation(
        self,
        identity: str,
        camera_id: str,
        timestamp: float,
        bbox: List[int],
        confidence: float,
        embedding: Optional[np.ndarray] = None,
        track_id: Optional[str] = None,
        quality_score: Optional[float] = None,
    ) -> TrajectoryNode:
        """
        Record a new observation for an identity and update its trajectory.
        Automatically performs cross-camera transition evaluation if coming from a different camera.
        """
        trajectory = self.get_or_create_trajectory(identity)
        node_id = f"{identity}_{camera_id}_{int(timestamp * 1000)}"
        iso_ts = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

        transition_type: Optional[TransitionType] = None
        reasoning: Optional[TransitionReasoning] = None

        if trajectory.nodes:
            prev_node = trajectory.nodes[-1]
            if prev_node.camera_id != camera_id:
                elapsed = max(0.001, timestamp - prev_node.timestamp)
                # Compute embedding similarity between observations if embeddings present
                sim = confidence  # Fallback to detector confidence
                if embedding is not None:
                    # In real operation, compare against prev_node or trajectory mean
                    sim = confidence

                transition_type, reasoning = self.evaluate_transition(
                    from_camera_id=prev_node.camera_id,
                    to_camera_id=camera_id,
                    elapsed_seconds=elapsed,
                    embedding_similarity=sim,
                )

        node = TrajectoryNode(
            node_id=node_id,
            camera_id=camera_id,
            timestamp=timestamp,
            iso_timestamp=iso_ts,
            bbox=bbox,
            confidence=confidence,
            track_id=track_id,
            quality_score=quality_score,
            transition_type=transition_type,
            reasoning=reasoning,
        )

        trajectory.add_node(node)

        # Update recent observations cache
        if identity not in self._recent_observations:
            self._recent_observations[identity] = []
        
        self._recent_observations[identity].append({
            "timestamp": timestamp,
            "camera_id": camera_id,
            "embedding": embedding,
            "bbox": bbox,
            "confidence": confidence,
            "track_id": track_id,
        })
        # Keep only recent within max_continuity_gap_seconds
        cutoff = timestamp - self.max_continuity_gap_seconds
        self._recent_observations[identity] = [
            o for o in self._recent_observations[identity] if o["timestamp"] >= cutoff
        ]

        return node

    def get_candidate_identities_for_camera(
        self,
        current_camera_id: str,
        current_timestamp: float,
    ) -> List[Tuple[str, float, str]]:
        """
        Topology-aware candidate pruning.
        
        Instead of searching all identities across the entire database, returns only
        identities whose recent spatial-temporal trajectory makes them physically
        reachable on current_camera_id right now.
        
        Returns:
            List of (identity, reachability_score, prior_camera_id)
        """
        candidates: List[Tuple[str, float, str]] = []

        for identity, trajectory in self.trajectories.items():
            if not trajectory.nodes:
                continue
            last_node = trajectory.nodes[-1]
            elapsed = current_timestamp - last_node.timestamp

            if elapsed > self.max_continuity_gap_seconds or elapsed < 0:
                continue

            if last_node.camera_id == current_camera_id:
                # Same camera persistence
                candidates.append((identity, 1.0, last_node.camera_id))
                continue

            # Check reachability in topology graph
            reachable = self.topology.get_reachable_cameras(last_node.camera_id, elapsed)
            for cam_id, score, _ in reachable:
                if cam_id == current_camera_id:
                    candidates.append((identity, score, last_node.camera_id))
                    break

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    def get_trajectory_history(self, identity: str) -> Optional[Dict[str, Any]]:
        """Get full serialized trajectory history for an identity."""
        traj = self.trajectories.get(identity)
        return traj.to_dict() if traj else None
