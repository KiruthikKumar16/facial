"""
Edge-Node Health Monitoring & Adaptive Runtime Controller.

Monitors edge system resources (CPU, GPU, memory, temperature, disk, FPS, network latency, queues)
and adaptively controls pipeline execution (frame sampling, batching, offline queuing, storage protection)
using hysteresis bands to prevent mode flapping.
"""

from __future__ import annotations

import enum
import logging
import os
import shutil
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RuntimeMode(str, enum.Enum):
    """Adaptive operational mode of the edge recognition runtime."""
    NORMAL = "NORMAL"
    THROTTLED_COMPUTE = "THROTTLED_COMPUTE"
    DEGRADED_NETWORK = "DEGRADED_NETWORK"
    OFFLINE = "OFFLINE"
    EMERGENCY_DISK_PRESSURE = "EMERGENCY_DISK_PRESSURE"


@dataclass
class NodeHealthMetrics:
    """Snapshot of edge node hardware, pipeline throughput, and network health."""
    cpu_percent: float = 0.0
    gpu_percent: Optional[float] = None
    memory_percent: float = 0.0
    temperature_celsius: Optional[float] = None
    disk_free_mb: float = 5000.0
    disk_percent: float = 0.0
    camera_fps: float = 30.0
    inference_fps: float = 30.0
    network_latency_ms: Optional[float] = 20.0
    is_online: bool = True
    sync_queue_length: int = 0
    event_backlog_count: int = 0
    recognition_latency_ms: float = 15.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "gpu_percent": round(self.gpu_percent, 1) if self.gpu_percent is not None else None,
            "memory_percent": round(self.memory_percent, 1),
            "temperature_celsius": round(self.temperature_celsius, 1) if self.temperature_celsius is not None else None,
            "disk_free_mb": round(self.disk_free_mb, 1),
            "disk_percent": round(self.disk_percent, 1),
            "camera_fps": round(self.camera_fps, 1),
            "inference_fps": round(self.inference_fps, 1),
            "network_latency_ms": round(self.network_latency_ms, 1) if self.network_latency_ms is not None else None,
            "is_online": self.is_online,
            "sync_queue_length": self.sync_queue_length,
            "event_backlog_count": self.event_backlog_count,
            "recognition_latency_ms": round(self.recognition_latency_ms, 1),
            "timestamp": self.timestamp,
        }


@dataclass
class RuntimeControllerConfig:
    """Configurable threshold policy for adaptive runtime control."""
    # Compute Load (CPU & Thermal)
    cpu_high_threshold: float = 85.0
    cpu_recovery_threshold: float = 70.0
    temp_high_threshold: float = 80.0
    temp_recovery_threshold: float = 70.0
    rec_latency_high_threshold_ms: float = 80.0
    rec_latency_recovery_threshold_ms: float = 40.0

    # Network Latency
    network_latency_high_ms: float = 500.0
    network_latency_recovery_ms: float = 150.0

    # Storage Pressure
    disk_low_mb_threshold: float = 500.0
    disk_recovery_mb_threshold: float = 1000.0

    # Hysteresis & Anti-Flapping
    consecutive_triggers_required: int = 3
    cooldown_seconds: float = 10.0

    # Runtime Adaptation Parameters
    normal_frame_sampling_rate: float = 1.0
    throttled_frame_sampling_rate: float = 0.33  # Process 1 in 3 frames under heavy compute load
    normal_batch_size: int = 5
    normal_batch_interval_s: float = 1.0
    degraded_batch_size: int = 25
    degraded_batch_interval_s: float = 5.0


@dataclass
class RuntimeDecision:
    """Audit log entry of an adaptive runtime decision."""
    timestamp: float
    previous_mode: RuntimeMode
    new_mode: RuntimeMode
    trigger_reason: str
    applied_parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "previous_mode": self.previous_mode.value,
            "new_mode": self.new_mode.value,
            "trigger_reason": self.trigger_reason,
            "applied_parameters": self.applied_parameters,
        }


class SystemHealthCollector:
    """Collects actual host OS health metrics."""

    @staticmethod
    def collect_live_metrics(
        disk_path: str = ".",
        camera_fps: float = 30.0,
        inference_fps: float = 30.0,
        network_latency_ms: Optional[float] = 25.0,
        is_online: bool = True,
        sync_queue_length: int = 0,
        event_backlog: int = 0,
        recognition_latency_ms: float = 15.0,
    ) -> NodeHealthMetrics:
        """Sample current system metrics with fallback for environments lacking psutil."""
        cpu = 0.0
        mem = 0.0
        temp = None
        disk_free_mb = 10000.0
        disk_percent = 20.0

        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            
            # Disk space
            disk_usage = psutil.disk_usage(disk_path)
            disk_free_mb = disk_usage.free / (1024 * 1024)
            disk_percent = disk_usage.percent

            # Temperatures if supported by hardware
            if hasattr(psutil, "sensors_temperatures"):
                sensors = psutil.sensors_temperatures()
                if sensors:
                    for name, entries in sensors.items():
                        if entries:
                            temp = entries[0].current
                            break
        except Exception:
            pass

        return NodeHealthMetrics(
            cpu_percent=cpu,
            memory_percent=mem,
            temperature_celsius=temp,
            disk_free_mb=disk_free_mb,
            disk_percent=disk_percent,
            camera_fps=camera_fps,
            inference_fps=inference_fps,
            network_latency_ms=network_latency_ms,
            is_online=is_online,
            sync_queue_length=sync_queue_length,
            event_backlog_count=event_backlog,
            recognition_latency_ms=recognition_latency_ms,
            timestamp=time.time(),
        )


class AdaptiveRuntimeController:
    """
    Evaluates node health against configured hysteresis thresholds and adapts
    the pipeline (frame sampling, batch intervals, network suppression, and storage alerts).
    """

    def __init__(
        self,
        config: Optional[RuntimeControllerConfig] = None,
        on_mode_change: Optional[Callable[[RuntimeMode, RuntimeMode, str], None]] = None,
        on_disk_alert: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        self.config = config or RuntimeControllerConfig()
        self.on_mode_change = on_mode_change
        self.on_disk_alert = on_disk_alert

        self.current_mode = RuntimeMode.NORMAL
        self.last_transition_time = time.time()
        self.decision_history: List[RuntimeDecision] = []

        # Hysteresis counters
        self._compute_trigger_count = 0
        self._network_trigger_count = 0
        self._disk_trigger_count = 0

        # Active parameters
        self.active_frame_sampling_rate: float = self.config.normal_frame_sampling_rate
        self.active_batch_size: int = self.config.normal_batch_size
        self.active_batch_interval_s: float = self.config.normal_batch_interval_s
        self.network_sync_enabled: bool = True
        self.emergency_storage_active: bool = False

    def evaluate_metrics(self, metrics: NodeHealthMetrics) -> RuntimeMode:
        """
        Evaluate metrics against hysteresis threshold bands and update runtime mode.
        """
        now = metrics.timestamp
        in_cooldown = (now - self.last_transition_time) < self.config.cooldown_seconds

        # 1. Evaluate Condition Triggers
        is_offline = not metrics.is_online
        is_disk_critical = metrics.disk_free_mb < self.config.disk_low_mb_threshold

        compute_stressed = (
            metrics.cpu_percent >= self.config.cpu_high_threshold
            or (metrics.temperature_celsius is not None and metrics.temperature_celsius >= self.config.temp_high_threshold)
            or metrics.recognition_latency_ms >= self.config.rec_latency_high_threshold_ms
        )

        network_stressed = (
            metrics.network_latency_ms is not None
            and metrics.network_latency_ms >= self.config.network_latency_high_ms
        )

        # Update hysteresis trigger counters
        self._compute_trigger_count = (self._compute_trigger_count + 1) if compute_stressed else max(0, self._compute_trigger_count - 1)
        self._network_trigger_count = (self._network_trigger_count + 1) if network_stressed else max(0, self._network_trigger_count - 1)
        self._disk_trigger_count = (self._disk_trigger_count + 1) if is_disk_critical else max(0, self._disk_trigger_count - 1)

        target_mode = self.current_mode

        # Priority 1: Emergency Disk Pressure (Never drop critical events, alert immediately!)
        if self._disk_trigger_count >= 1:
            target_mode = RuntimeMode.EMERGENCY_DISK_PRESSURE
            if self.on_disk_alert:
                self.on_disk_alert(metrics.disk_free_mb, f"Low disk space: {metrics.disk_free_mb:.1f} MB remaining")

        # Priority 2: Offline Connectivity
        elif is_offline:
            target_mode = RuntimeMode.OFFLINE

        # Priority 3: Compute Overload
        elif self._compute_trigger_count >= self.config.consecutive_triggers_required:
            target_mode = RuntimeMode.THROTTLED_COMPUTE

        # Priority 4: High Network Latency
        elif self._network_trigger_count >= self.config.consecutive_triggers_required:
            target_mode = RuntimeMode.DEGRADED_NETWORK

        # Recovery Logic (requires dropping below recovery threshold and exiting cooldown)
        elif not in_cooldown:
            # Check recovery conditions
            can_recover_from_compute = (
                metrics.cpu_percent < self.config.cpu_recovery_threshold
                and (metrics.temperature_celsius is None or metrics.temperature_celsius < self.config.temp_recovery_threshold)
                and metrics.recognition_latency_ms < self.config.rec_latency_recovery_threshold_ms
            )
            can_recover_from_network = (
                metrics.network_latency_ms is None
                or metrics.network_latency_ms < self.config.network_latency_recovery_ms
            )
            can_recover_from_disk = metrics.disk_free_mb > self.config.disk_recovery_mb_threshold

            if self.current_mode == RuntimeMode.THROTTLED_COMPUTE and can_recover_from_compute:
                target_mode = RuntimeMode.NORMAL
            elif self.current_mode == RuntimeMode.DEGRADED_NETWORK and can_recover_from_network:
                target_mode = RuntimeMode.NORMAL
            elif self.current_mode == RuntimeMode.OFFLINE and metrics.is_online:
                target_mode = RuntimeMode.NORMAL
            elif self.current_mode == RuntimeMode.EMERGENCY_DISK_PRESSURE and can_recover_from_disk:
                target_mode = RuntimeMode.NORMAL

        # Execute Mode Transition if changed
        if target_mode != self.current_mode:
            self._apply_mode_transition(target_mode, metrics)

        return self.current_mode

    def _apply_mode_transition(self, new_mode: RuntimeMode, metrics: NodeHealthMetrics) -> None:
        """Apply operational parameter adjustments for the new mode."""
        old_mode = self.current_mode
        self.current_mode = new_mode
        self.last_transition_time = metrics.timestamp

        reason = ""
        applied_params = {}

        if new_mode == RuntimeMode.NORMAL:
            self.active_frame_sampling_rate = self.config.normal_frame_sampling_rate
            self.active_batch_size = self.config.normal_batch_size
            self.active_batch_interval_s = self.config.normal_batch_interval_s
            self.network_sync_enabled = True
            self.emergency_storage_active = False
            reason = "Resources recovered within nominal bounds."

        elif new_mode == RuntimeMode.THROTTLED_COMPUTE:
            # Reduce frame sampling rate to shed compute load
            self.active_frame_sampling_rate = self.config.throttled_frame_sampling_rate
            self.network_sync_enabled = True
            self.emergency_storage_active = False
            reason = (
                f"High compute load detected (CPU: {metrics.cpu_percent:.1f}%, "
                f"Rec Latency: {metrics.recognition_latency_ms:.1f}ms). Throttling frame sampling to {self.active_frame_sampling_rate:.2f}x."
            )

        elif new_mode == RuntimeMode.DEGRADED_NETWORK:
            # Increase batch size and interval to reduce HTTP connection overhead
            self.active_batch_size = self.config.degraded_batch_size
            self.active_batch_interval_s = self.config.degraded_batch_interval_s
            self.network_sync_enabled = True
            self.emergency_storage_active = False
            reason = (
                f"High network latency detected ({metrics.network_latency_ms:.1f}ms). "
                f"Increasing batching to {self.active_batch_size} events / {self.active_batch_interval_s:.1f}s."
            )

        elif new_mode == RuntimeMode.OFFLINE:
            # Disable live network attempts and rely solely on local SQLite ledger
            self.network_sync_enabled = False
            self.emergency_storage_active = False
            reason = "Edge node is offline. Disabling live network requests; buffering events locally."

        elif new_mode == RuntimeMode.EMERGENCY_DISK_PRESSURE:
            # Protect critical events (VIP, Watchlist, Alerts) and alert operator
            self.emergency_storage_active = True
            reason = (
                f"Critical storage pressure ({metrics.disk_free_mb:.1f}MB free < {self.config.disk_low_mb_threshold:.1f}MB). "
                f"Engaging critical event protection and storage alerts."
            )

        applied_params = {
            "frame_sampling_rate": self.active_frame_sampling_rate,
            "batch_size": self.active_batch_size,
            "batch_interval_s": self.active_batch_interval_s,
            "network_sync_enabled": self.network_sync_enabled,
            "emergency_storage_active": self.emergency_storage_active,
        }

        decision = RuntimeDecision(
            timestamp=metrics.timestamp,
            previous_mode=old_mode,
            new_mode=new_mode,
            trigger_reason=reason,
            applied_parameters=applied_params,
        )
        self.decision_history.append(decision)
        logger.info(f"Adaptive Runtime Transition: {old_mode.value} -> {new_mode.value} | {reason}")

        if self.on_mode_change:
            try:
                self.on_mode_change(old_mode, new_mode, reason)
            except Exception as e:
                logger.error(f"Mode change callback failed: {e}")

    def should_process_frame(self, frame_index: int) -> bool:
        """Determine if a camera frame should be processed based on active sampling rate."""
        if self.active_frame_sampling_rate >= 0.99:
            return True
        step = int(round(1.0 / self.active_frame_sampling_rate))
        return (frame_index % max(1, step)) == 0

    def should_preserve_event(self, priority: str) -> bool:
        """
        CRITICAL RULE: Critical security events (high/critical/VIP/alert) are NEVER discarded!
        Only debug or unflagged transient telemetry may be pruned under extreme disk pressure.
        """
        if not self.emergency_storage_active:
            return True
        # Under emergency disk pressure:
        return priority.lower() in ("critical", "high", "alert", "vip", "blacklist")
