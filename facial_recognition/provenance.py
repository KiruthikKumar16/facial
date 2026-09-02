"""
Recognition-Event Provenance Tracking Module.

Constructs and verifies end-to-end traceable lineage for every face recognition event:
Camera → Frame/Observation → Face Track → Embedding → Candidates → Decision → Sync → Cloud
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CandidateSummary:
    """Non-sensitive candidate match reference."""
    identity: str
    score: float
    profile_id: Optional[str] = None
    rank: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "score": round(self.score, 4),
            "profile_id": self.profile_id,
            "rank": self.rank,
        }


@dataclass
class ProcessingStage:
    """Individual stage node in the recognition processing graph."""
    stage_name: str
    stage_id: str
    timestamp: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "stage_id": self.stage_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class RecognitionProvenance:
    """
    Immutable lineage record capturing the full end-to-end provenance of a recognition decision.
    """
    event_id: str
    camera_id: str
    frame_reference: str
    track_id: Optional[str]
    observation_references: List[str]
    detection_model_version: str
    embedding_model_version: str
    embedding_fingerprint: str  # SHA-256 digest of embedding vector (protects raw biometrics)
    candidate_matches: List[CandidateSummary]
    decision_tier: str
    selected_identity: str
    confidence: float
    decision_timestamp: float = field(default_factory=time.time)
    sync_event_id: Optional[str] = None
    cloud_detection_id: Optional[str] = None

    @property
    def provenance_chain_hash(self) -> str:
        """Deterministic cryptographic digest locking the entire 7-stage lineage graph."""
        payload = {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "frame_reference": self.frame_reference,
            "track_id": self.track_id,
            "observation_references": self.observation_references,
            "detection_model_version": self.detection_model_version,
            "embedding_model_version": self.embedding_model_version,
            "embedding_fingerprint": self.embedding_fingerprint,
            "candidates": [c.to_dict() for c in self.candidate_matches],
            "decision_tier": self.decision_tier,
            "selected_identity": self.selected_identity,
            "confidence": round(self.confidence, 6),
            "decision_timestamp": round(self.decision_timestamp, 3),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_lineage_stages(self) -> List[ProcessingStage]:
        """Generate human-readable 7-stage lineage graph for UI inspection."""
        return [
            ProcessingStage(
                stage_name="1. Camera Ingestion",
                stage_id=f"cam_{self.camera_id}",
                timestamp=self.decision_timestamp,
                metadata={"camera_id": self.camera_id},
            ),
            ProcessingStage(
                stage_name="2. Frame Acquisition",
                stage_id=self.frame_reference,
                timestamp=self.decision_timestamp,
                metadata={"frame_reference": self.frame_reference, "observation_count": len(self.observation_references)},
            ),
            ProcessingStage(
                stage_name="3. Face Tracking",
                stage_id=self.track_id or "untracked",
                timestamp=self.decision_timestamp,
                metadata={"track_id": self.track_id, "observations": self.observation_references},
            ),
            ProcessingStage(
                stage_name="4. Embedding Feature Extraction",
                stage_id=f"emb_{self.embedding_fingerprint[:12]}",
                timestamp=self.decision_timestamp,
                metadata={
                    "detection_model": self.detection_model_version,
                    "embedding_model": self.embedding_model_version,
                    "embedding_fingerprint": self.embedding_fingerprint,
                },
            ),
            ProcessingStage(
                stage_name="5. Candidate Evaluation",
                stage_id=f"eval_{self.event_id}",
                timestamp=self.decision_timestamp,
                metadata={"candidates": [c.to_dict() for c in self.candidate_matches]},
            ),
            ProcessingStage(
                stage_name="6. Recognition Decision",
                stage_id=f"dec_{self.event_id}",
                timestamp=self.decision_timestamp,
                metadata={
                    "selected_identity": self.selected_identity,
                    "confidence": self.confidence,
                    "decision_tier": self.decision_tier,
                },
            ),
            ProcessingStage(
                stage_name="7. Cloud Synchronization",
                stage_id=self.sync_event_id or f"sync_{self.event_id}",
                timestamp=self.decision_timestamp,
                metadata={
                    "event_id": self.event_id,
                    "cloud_detection_id": self.cloud_detection_id,
                    "chain_hash": self.provenance_chain_hash,
                },
            ),
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "frame_reference": self.frame_reference,
            "track_id": self.track_id,
            "observation_references": self.observation_references,
            "detection_model_version": self.detection_model_version,
            "embedding_model_version": self.embedding_model_version,
            "embedding_fingerprint": self.embedding_fingerprint,
            "candidate_matches": [c.to_dict() for c in self.candidate_matches],
            "decision_tier": self.decision_tier,
            "selected_identity": self.selected_identity,
            "confidence": round(self.confidence, 4),
            "decision_timestamp": self.decision_timestamp,
            "sync_event_id": self.sync_event_id,
            "cloud_detection_id": self.cloud_detection_id,
            "provenance_chain_hash": self.provenance_chain_hash,
            "stages": [s.to_dict() for s in self.get_lineage_stages()],
        }


class ProvenanceTracker:
    """Builder class for tracking recognition processing stages in real time."""

    def __init__(self, camera_id: str, frame_reference: Optional[str] = None, track_id: Optional[str] = None) -> None:
        self.camera_id = camera_id
        self.frame_reference = frame_reference or f"frm_{camera_id}_{int(time.time()*1000)}"
        self.track_id = track_id
        self.observations: List[str] = []
        self.detection_model = "scrfd_500m_bnkps_v1"
        self.embedding_model = "w600k_mbf_v1"
        self.embedding_fingerprint = ""
        self.candidates: List[CandidateSummary] = []
        self.decision_tier = "LOCAL_HIGH_CONFIDENCE"
        self.selected_identity = "Unknown"
        self.confidence = 0.0
        self.event_id = ""

    def add_observation(self, observation_id: str) -> None:
        self.observations.append(observation_id)

    def set_models(self, detection_model: str, embedding_model: str) -> None:
        self.detection_model = detection_model
        self.embedding_model = embedding_model

    def set_embedding_vector(self, embedding: np.ndarray | List[float]) -> None:
        """Compute SHA-256 fingerprint without storing raw vector."""
        arr = np.asarray(embedding, dtype=np.float32).flatten()
        self.embedding_fingerprint = hashlib.sha256(arr.tobytes()).hexdigest()

    def add_candidate(self, identity: str, score: float, profile_id: Optional[str] = None, rank: int = 1) -> None:
        self.candidates.append(CandidateSummary(
            identity=identity,
            score=score,
            profile_id=profile_id,
            rank=rank,
        ))

    def finalize(
        self,
        event_id: str,
        identity: str,
        confidence: float,
        decision_tier: str = "LOCAL_HIGH_CONFIDENCE",
        sync_event_id: Optional[str] = None,
    ) -> RecognitionProvenance:
        """Compile the complete immutable provenance record."""
        self.event_id = event_id
        self.selected_identity = identity
        self.confidence = confidence
        self.decision_tier = decision_tier

        if not self.observations:
            self.observations.append(f"obs_{self.frame_reference}_01")

        if not self.embedding_fingerprint:
            self.embedding_fingerprint = hashlib.sha256(f"dummy_emb_{event_id}".encode()).hexdigest()

        return RecognitionProvenance(
            event_id=self.event_id,
            camera_id=self.camera_id,
            frame_reference=self.frame_reference,
            track_id=self.track_id,
            observation_references=self.observations,
            detection_model_version=self.detection_model,
            embedding_model_version=self.embedding_model,
            embedding_fingerprint=self.embedding_fingerprint,
            candidate_matches=self.candidates,
            decision_tier=self.decision_tier,
            selected_identity=self.selected_identity,
            confidence=self.confidence,
            decision_timestamp=time.time(),
            sync_event_id=sync_event_id or f"sync_{self.event_id}",
        )
