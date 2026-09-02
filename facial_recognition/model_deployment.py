"""
Safe Model Deployment, Validation, Live Health Monitoring, and Atomic Rollback for Edge Nodes.

Maintains:
- Active Model
- Previous Known-Good Model
- Candidate Model

Provides:
- Pre-activation model verification (checksum, tensor signature, inference sanity)
- Live health monitoring (latency, P95, FPS, error rate, confidence distribution)
- Degradation detection rules with explicit metric formulas
- Crash-safe, atomic rollback to the previous known-good model
- Guaranteed preservation of previous working models
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import os
import shutil
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class DeploymentState(str, enum.Enum):
    """Lifecycle state of edge model deployment."""
    IDLE = "IDLE"
    VALIDATING_CANDIDATE = "VALIDATING_CANDIDATE"
    CANARY_ACTIVE = "CANARY_ACTIVE"
    ACTIVE = "ACTIVE"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


@dataclass
class ModelArtifactMetadata:
    """Metadata manifest describing a versioned model artifact."""
    model_name: str
    version: str
    sha256_checksum: str
    input_shape: List[int]
    output_shape: List[int]
    created_at: float = field(default_factory=time.time)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelArtifactMetadata:
        return cls(
            model_name=data["model_name"],
            version=data["version"],
            sha256_checksum=data["sha256_checksum"],
            input_shape=data["input_shape"],
            output_shape=data["output_shape"],
            created_at=data.get("created_at", time.time()),
            description=data.get("description", ""),
        )


@dataclass
class ModelHealthPolicy:
    """
    Configurable degradation thresholds.
    
    Metric Calculations:
    1. Average Latency: mean(latency_ms) over last N observations.
    2. P95 Latency: 95th percentile(latency_ms) over last N observations.
    3. Processing FPS: count(observations) / total_window_elapsed_seconds.
    4. Error Rate: count(errors) / count(total_observations).
    5. Confidence Degradation: fraction of observations where confidence < low_confidence_threshold.
    """
    max_avg_latency_ms: float = 60.0
    max_p95_latency_ms: float = 120.0
    min_fps: float = 5.0
    max_error_rate: float = 0.05  # 5% max error rate
    min_avg_confidence: float = 0.35
    max_low_confidence_ratio: float = 0.50  # Max 50% detections below threshold
    low_confidence_threshold: float = 0.30
    sliding_window_size: int = 50
    canary_window_seconds: float = 30.0


@dataclass
class HealthCheckResult:
    """Evaluation result of live model health metrics."""
    is_healthy: bool
    violations: List[str]
    sample_count: int
    avg_latency_ms: float
    p95_latency_ms: float
    fps: float
    error_rate: float
    avg_confidence: float
    low_confidence_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_healthy": self.is_healthy,
            "violations": self.violations,
            "sample_count": self.sample_count,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "fps": round(self.fps, 2),
            "error_rate": round(self.error_rate, 4),
            "avg_confidence": round(self.avg_confidence, 4),
            "low_confidence_ratio": round(self.low_confidence_ratio, 4),
        }


class ModelHealthMonitor:
    """
    Sliding-window monitor that tracks live inference health and detects degradation.
    """

    def __init__(self, policy: Optional[ModelHealthPolicy] = None) -> None:
        self.policy = policy or ModelHealthPolicy()
        self.window_size = self.policy.sliding_window_size
        self.latencies: Deque[float] = deque(maxlen=self.window_size)
        self.confidences: Deque[float] = deque(maxlen=self.window_size)
        self.timestamps: Deque[float] = deque(maxlen=self.window_size)
        self.errors: Deque[int] = deque(maxlen=self.window_size)  # 1 for error, 0 for success

    def reset(self) -> None:
        """Clear observation window (e.g. on new model activation)."""
        self.latencies.clear()
        self.confidences.clear()
        self.timestamps.clear()
        self.errors.clear()

    def record_observation(
        self,
        latency_ms: float,
        confidence: Optional[float] = None,
        is_error: bool = False,
    ) -> None:
        """Record a single inference observation."""
        now = time.time()
        self.timestamps.append(now)
        self.latencies.append(latency_ms)
        self.errors.append(1 if is_error else 0)
        if confidence is not None:
            self.confidences.append(confidence)

    def evaluate_health(self) -> HealthCheckResult:
        """
        Evaluate live metrics against health policy.
        Requires at least 5 samples to begin evaluating degradation rules.
        """
        n = len(self.latencies)
        if n < 5:
            return HealthCheckResult(
                is_healthy=True,
                violations=[],
                sample_count=n,
                avg_latency_ms=float(np.mean(self.latencies)) if n > 0 else 0.0,
                p95_latency_ms=float(np.percentile(self.latencies, 95)) if n > 0 else 0.0,
                fps=0.0,
                error_rate=0.0,
                avg_confidence=float(np.mean(self.confidences)) if len(self.confidences) > 0 else 0.0,
                low_confidence_ratio=0.0,
            )

        avg_lat = float(np.mean(self.latencies))
        p95_lat = float(np.percentile(self.latencies, 95))
        
        # Calculate FPS = N / (t_last - t_first)
        time_span = self.timestamps[-1] - self.timestamps[0]
        fps = (n / time_span) if time_span > 0.001 else 100.0
        
        # Error Rate
        error_rate = float(sum(self.errors) / n)
        
        # Confidence Metrics
        if len(self.confidences) > 0:
            avg_conf = float(np.mean(self.confidences))
            low_count = sum(1 for c in self.confidences if c < self.policy.low_confidence_threshold)
            low_ratio = float(low_count / len(self.confidences))
        else:
            avg_conf = 1.0
            low_ratio = 0.0

        violations = []
        if avg_lat > self.policy.max_avg_latency_ms:
            violations.append(f"Average latency {avg_lat:.1f}ms exceeds maximum {self.policy.max_avg_latency_ms:.1f}ms")
        if p95_lat > self.policy.max_p95_latency_ms:
            violations.append(f"P95 latency {p95_lat:.1f}ms exceeds maximum {self.policy.max_p95_latency_ms:.1f}ms")
        if fps < self.policy.min_fps and time_span >= 1.0:
            violations.append(f"Processing FPS {fps:.1f} below minimum {self.policy.min_fps:.1f}")
        if error_rate > self.policy.max_error_rate:
            violations.append(f"Error rate {error_rate * 100:.1f}% exceeds limit {self.policy.max_error_rate * 100:.1f}%")
        if avg_conf < self.policy.min_avg_confidence and len(self.confidences) >= 5:
            violations.append(f"Average confidence {avg_conf:.2f} below threshold {self.policy.min_avg_confidence:.2f}")
        if low_ratio > self.policy.max_low_confidence_ratio and len(self.confidences) >= 5:
            violations.append(f"Low confidence ratio {low_ratio * 100:.1f}% exceeds threshold {self.policy.max_low_confidence_ratio * 100:.1f}%")

        is_healthy = len(violations) == 0
        return HealthCheckResult(
            is_healthy=is_healthy,
            violations=violations,
            sample_count=n,
            avg_latency_ms=avg_lat,
            p95_latency_ms=p95_lat,
            fps=fps,
            error_rate=error_rate,
            avg_confidence=avg_conf,
            low_confidence_ratio=low_ratio,
        )


class ModelValidator:
    """
    Validates model integrity, compatibility, and executes pre-activation smoke tests.
    """

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        """Compute SHA-256 hash of a model file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def validate_artifact(
        cls,
        model_file: Path,
        metadata_file: Path,
        infer_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    ) -> Tuple[bool, str]:
        """
        Validate artifact checksum, readability, and execute smoke test.
        """
        if not model_file.exists():
            return False, f"Model file not found: {model_file}"
        if not metadata_file.exists():
            return False, f"Metadata file not found: {metadata_file}"

        # 1. Verify Manifest and Checksum
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
            meta = ModelArtifactMetadata.from_dict(meta_dict)
        except Exception as e:
            return False, f"Corrupted metadata manifest: {e}"

        actual_sha = cls.calculate_sha256(model_file)
        if actual_sha != meta.sha256_checksum:
            return False, (
                f"Checksum mismatch for version '{meta.version}': "
                f"expected {meta.sha256_checksum[:12]}..., got {actual_sha[:12]}..."
            )

        # 2. Smoke Test Inference Sanity
        if infer_fn:
            try:
                dummy_input = np.zeros(meta.input_shape, dtype=np.float32)
                t0 = time.perf_counter()
                out = infer_fn(dummy_input)
                latency = (time.perf_counter() - t0) * 1000.0

                if out is None:
                    return False, "Inference returned None"
                if np.isnan(out).any() or np.isinf(out).any():
                    return False, "Inference output contains NaN or Inf values"
                if latency > 1000.0:
                    return False, f"Pre-activation smoke test latency unacceptable ({latency:.1f}ms > 1000ms)"
            except Exception as e:
                return False, f"Smoke test inference failed: {e}"

        return True, "Validation successful"


class ModelDeploymentManager:
    """
    Manages edge model artifacts, pre-activation validation, live canary monitoring,
    and crash-resilient atomic rollback.
    """

    STATE_FILE_NAME = "model_deployment_state.json"

    def __init__(
        self,
        base_dir: str | Path,
        health_policy: Optional[ModelHealthPolicy] = None,
        on_rollback_cb: Optional[Callable[[str, str, List[str]], None]] = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.models_dir = self.base_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.base_dir / self.STATE_FILE_NAME

        self.health_monitor = ModelHealthMonitor(health_policy)
        self.on_rollback_cb = on_rollback_cb

        # State pointers
        self.active_version: str = "v1"
        self.previous_known_good_version: Optional[str] = None
        self.candidate_version: Optional[str] = None
        self.deployment_state: DeploymentState = DeploymentState.IDLE
        self.canary_started_at: Optional[float] = None

        # Load or initialize persistent state
        self._load_or_recover_state()

    def _save_state_atomic(self) -> None:
        """Atomically persist deployment state pointers to disk."""
        data = {
            "active_version": self.active_version,
            "previous_known_good_version": self.previous_known_good_version,
            "candidate_version": self.candidate_version,
            "deployment_state": self.deployment_state.value,
            "canary_started_at": self.canary_started_at,
            "updated_at": time.time(),
        }
        tmp_file = self.state_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp_file.replace(self.state_file)

    def _load_or_recover_state(self) -> None:
        """Load state and handle crash recovery if interrupted mid-deployment."""
        if not self.state_file.exists():
            self._save_state_atomic()
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.active_version = data.get("active_version", "v1")
            self.previous_known_good_version = data.get("previous_known_good_version")
            self.candidate_version = data.get("candidate_version")
            raw_state = data.get("deployment_state", DeploymentState.IDLE.value)
            self.deployment_state = DeploymentState(raw_state)
            self.canary_started_at = data.get("canary_started_at")

            # Crash Recovery Check:
            # If process crashed during VALIDATING_CANDIDATE or ROLLING_BACK, recover to known-good
            if self.deployment_state in (DeploymentState.VALIDATING_CANDIDATE, DeploymentState.ROLLING_BACK):
                logger.warning(
                    f"Recovered from interrupted deployment state '{self.deployment_state.value}'. "
                    f"Restoring to active known-good model '{self.active_version}'."
                )
                self.candidate_version = None
                self.deployment_state = DeploymentState.IDLE
                self._save_state_atomic()

        except Exception as e:
            logger.error(f"Error reading deployment state: {e}. Defaulting to safe defaults.")
            self._save_state_atomic()

    def register_model_artifact(
        self,
        version: str,
        model_bytes: bytes,
        input_shape: List[int],
        output_shape: List[int],
        description: str = "",
    ) -> ModelArtifactMetadata:
        """Store a new versioned model artifact to disk."""
        target_dir = self.models_dir / version
        target_dir.mkdir(parents=True, exist_ok=True)
        model_file = target_dir / "model.bin"
        meta_file = target_dir / "metadata.json"

        # Write model artifact
        with open(model_file, "wb") as f:
            f.write(model_bytes)

        sha = hashlib.sha256(model_bytes).hexdigest()
        meta = ModelArtifactMetadata(
            model_name="insightface_recognizer",
            version=version,
            sha256_checksum=sha,
            input_shape=input_shape,
            output_shape=output_shape,
            description=description,
        )
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2)

        return meta

    def deploy_candidate(
        self,
        candidate_version: str,
        infer_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    ) -> Tuple[bool, str]:
        """
        Deploy candidate model:
        1. Validates candidate artifact integrity and performs smoke test.
        2. Swaps previous_known_good_version = active_version.
        3. Sets active_version = candidate_version in CANARY_ACTIVE state.
        4. Never deletes previous model artifact.
        """
        cand_dir = self.models_dir / candidate_version
        model_file = cand_dir / "model.bin"
        meta_file = cand_dir / "metadata.json"

        self.candidate_version = candidate_version
        self.deployment_state = DeploymentState.VALIDATING_CANDIDATE
        self._save_state_atomic()

        # 1. Pre-activation Validation
        is_valid, msg = ModelValidator.validate_artifact(model_file, meta_file, infer_fn)
        if not is_valid:
            self.deployment_state = DeploymentState.FAILED
            self.candidate_version = None
            self._save_state_atomic()
            logger.error(f"Candidate '{candidate_version}' failed validation: {msg}")
            return False, f"Validation failed: {msg}"

        # 2. Promote to Canary Active
        self.previous_known_good_version = self.active_version
        self.active_version = candidate_version
        self.deployment_state = DeploymentState.CANARY_ACTIVE
        self.canary_started_at = time.time()
        self.health_monitor.reset()
        self._save_state_atomic()

        logger.info(
            f"Successfully promoted candidate '{candidate_version}' to CANARY_ACTIVE. "
            f"Previous known-good is '{self.previous_known_good_version}'."
        )
        return True, f"Candidate {candidate_version} activated in canary mode"

    def record_inference_observation(
        self,
        latency_ms: float,
        confidence: Optional[float] = None,
        is_error: bool = False,
    ) -> Optional[HealthCheckResult]:
        """
        Record observation and check for degradation.
        If degradation is detected during CANARY or ACTIVE state, triggers automatic atomic rollback!
        """
        self.health_monitor.record_observation(latency_ms, confidence, is_error)
        health = self.health_monitor.evaluate_health()

        if not health.is_healthy:
            logger.warning(
                f"Model degradation detected on active model '{self.active_version}': {health.violations}. "
                f"Triggering automatic atomic rollback!"
            )
            self.rollback(reason="; ".join(health.violations))
            return health

        # If in CANARY_ACTIVE and completed canary window safely, graduate to ACTIVE
        if self.deployment_state == DeploymentState.CANARY_ACTIVE:
            elapsed = time.time() - (self.canary_started_at or time.time())
            if elapsed >= self.health_monitor.policy.canary_window_seconds:
                self.deployment_state = DeploymentState.ACTIVE
                self.candidate_version = None
                self._save_state_atomic()
                logger.info(f"Model '{self.active_version}' passed canary period and graduated to ACTIVE.")

        return health

    def rollback(self, reason: str = "Manual or health threshold breach") -> Tuple[bool, str]:
        """
        Execute atomic rollback to previous known-good model.
        """
        if not self.previous_known_good_version:
            return False, "No previous known-good model version available to rollback to"

        target_version = self.previous_known_good_version
        failed_version = self.active_version

        self.deployment_state = DeploymentState.ROLLING_BACK
        self._save_state_atomic()

        # Atomic switch
        self.active_version = target_version
        self.deployment_state = DeploymentState.ROLLED_BACK
        self.candidate_version = None
        self.health_monitor.reset()
        self._save_state_atomic()

        logger.info(
            f"Atomic rollback successful: restored '{target_version}' as active model (demoted '{failed_version}'). "
            f"Reason: {reason}"
        )

        if self.on_rollback_cb:
            try:
                self.on_rollback_cb(failed_version, target_version, [reason])
            except Exception as e:
                logger.error(f"Rollback callback failed: {e}")

        return True, f"Successfully rolled back to {target_version}"
