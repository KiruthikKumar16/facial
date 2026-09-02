"""
Tests for Edge Node Health Monitoring and Adaptive Runtime Controller.

Covers:
1. Nominal Health / NORMAL mode operations
2. High Compute Load -> THROTTLED_COMPUTE & frame sampling reduction
3. High Network Latency -> DEGRADED_NETWORK & batching scale-up
4. Offline Condition -> OFFLINE mode & live sync suppression
5. Emergency Disk Pressure -> Operator alert & Critical Event Protection
6. Hysteresis Anti-Flapping Verification (Threshold separation + cooldown timer)
7. Runtime Decision Audit Logging
"""

import time
import pytest
from facial_recognition.runtime_controller import (
    AdaptiveRuntimeController,
    NodeHealthMetrics,
    RuntimeControllerConfig,
    RuntimeMode,
)


@pytest.fixture
def controller():
    config = RuntimeControllerConfig(
        cpu_high_threshold=85.0,
        cpu_recovery_threshold=70.0,
        temp_high_threshold=80.0,
        temp_recovery_threshold=70.0,
        rec_latency_high_threshold_ms=80.0,
        rec_latency_recovery_threshold_ms=40.0,
        network_latency_high_ms=500.0,
        network_latency_recovery_ms=150.0,
        disk_low_mb_threshold=500.0,
        disk_recovery_mb_threshold=1000.0,
        consecutive_triggers_required=3,
        cooldown_seconds=0.1,  # Short cooldown for test speed
        normal_frame_sampling_rate=1.0,
        throttled_frame_sampling_rate=0.33,
        normal_batch_size=5,
        normal_batch_interval_s=1.0,
        degraded_batch_size=25,
        degraded_batch_interval_s=5.0,
    )
    return AdaptiveRuntimeController(config=config)


# ==================== 1. Resource Condition Tests ====================

def test_nominal_health_operates_in_normal_mode(controller):
    """Under nominal conditions, controller remains in NORMAL mode with 1.0x frame sampling."""
    metrics = NodeHealthMetrics(
        cpu_percent=45.0,
        memory_percent=50.0,
        disk_free_mb=5000.0,
        network_latency_ms=30.0,
        is_online=True,
        recognition_latency_ms=20.0,
    )
    mode = controller.evaluate_metrics(metrics)
    assert mode == RuntimeMode.NORMAL
    assert controller.active_frame_sampling_rate == 1.0
    assert controller.active_batch_size == 5
    assert controller.network_sync_enabled is True
    assert controller.should_process_frame(0) is True
    assert controller.should_process_frame(1) is True


def test_high_compute_load_reduces_frame_sampling(controller):
    """High CPU (> 85%) for 3 consecutive cycles transitions to THROTTLED_COMPUTE (1 in 3 frames)."""
    high_cpu_metrics = NodeHealthMetrics(
        cpu_percent=92.0,
        memory_percent=60.0,
        disk_free_mb=5000.0,
        network_latency_ms=30.0,
        is_online=True,
        recognition_latency_ms=25.0,
    )

    # 1st cycle: counter = 1 (remains NORMAL)
    assert controller.evaluate_metrics(high_cpu_metrics) == RuntimeMode.NORMAL
    # 2nd cycle: counter = 2 (remains NORMAL)
    assert controller.evaluate_metrics(high_cpu_metrics) == RuntimeMode.NORMAL
    # 3rd cycle: counter = 3 (transitions to THROTTLED_COMPUTE)
    assert controller.evaluate_metrics(high_cpu_metrics) == RuntimeMode.THROTTLED_COMPUTE

    assert controller.active_frame_sampling_rate == 0.33
    # Verifying 1 in 3 frame processing:
    assert controller.should_process_frame(0) is True
    assert controller.should_process_frame(1) is False
    assert controller.should_process_frame(2) is False
    assert controller.should_process_frame(3) is True


def test_high_network_latency_increases_batching(controller):
    """High network latency (> 500ms) for 3 cycles scales batch size to 25 and interval to 5.0s."""
    high_latency_metrics = NodeHealthMetrics(
        cpu_percent=40.0,
        memory_percent=50.0,
        disk_free_mb=5000.0,
        network_latency_ms=750.0,  # > 500ms
        is_online=True,
    )

    for _ in range(2):
        controller.evaluate_metrics(high_latency_metrics)
    mode = controller.evaluate_metrics(high_latency_metrics)

    assert mode == RuntimeMode.DEGRADED_NETWORK
    assert controller.active_batch_size == 25
    assert controller.active_batch_interval_s == 5.0
    assert controller.network_sync_enabled is True


def test_offline_connectivity_disables_live_sync(controller):
    """Offline state immediately transitions to OFFLINE mode, pausing network attempts."""
    offline_metrics = NodeHealthMetrics(
        is_online=False,
        network_latency_ms=None,
    )
    mode = controller.evaluate_metrics(offline_metrics)
    assert mode == RuntimeMode.OFFLINE
    assert controller.network_sync_enabled is False


def test_emergency_disk_pressure_protects_critical_events(controller):
    """
    Low disk space (< 500MB) triggers EMERGENCY_DISK_PRESSURE and alerts operator.
    Guarantees that critical security events (VIP, Watchlist, Alerts) are strictly preserved!
    """
    alert_triggered = False
    alert_msg = ""
    def mock_alert(free_mb, msg):
        nonlocal alert_triggered, alert_msg
        alert_triggered = True
        alert_msg = msg

    controller.on_disk_alert = mock_alert

    low_disk_metrics = NodeHealthMetrics(
        disk_free_mb=250.0,  # < 500MB threshold
        is_online=True,
    )
    mode = controller.evaluate_metrics(low_disk_metrics)

    assert mode == RuntimeMode.EMERGENCY_DISK_PRESSURE
    assert alert_triggered is True
    assert "250.0 MB" in alert_msg
    assert controller.emergency_storage_active is True

    # Critical security events are NEVER discarded:
    assert controller.should_preserve_event("critical") is True
    assert controller.should_preserve_event("high") is True
    assert controller.should_preserve_event("alert") is True
    assert controller.should_preserve_event("vip") is True
    assert controller.should_preserve_event("blacklist") is True

    # Low priority / debug logs may be pruned:
    assert controller.should_preserve_event("debug") is False
    assert controller.should_preserve_event("low") is False


# ==================== 2. Hysteresis Anti-Flapping & Logging ====================

def test_hysteresis_prevents_flapping(controller):
    """
    Fluctuating CPU (e.g. 86% -> 84% -> 86%) does not flap back and forth,
    requiring drop below recovery threshold (70%) to return to NORMAL.
    """
    # 1. Trigger THROTTLED_COMPUTE with 90% CPU
    high_cpu = NodeHealthMetrics(cpu_percent=90.0, is_online=True)
    for _ in range(3):
        controller.evaluate_metrics(high_cpu)
    assert controller.current_mode == RuntimeMode.THROTTLED_COMPUTE

    # 2. CPU drops to 80% (below 85% high threshold, but ABOVE 70% recovery threshold!)
    time.sleep(0.15)  # Exit cooldown
    mid_cpu = NodeHealthMetrics(cpu_percent=80.0, is_online=True)
    controller.evaluate_metrics(mid_cpu)
    
    # Mode MUST remain THROTTLED_COMPUTE (hysteresis prevents premature return to NORMAL)
    assert controller.current_mode == RuntimeMode.THROTTLED_COMPUTE

    # 3. CPU drops to 60% (below 70% recovery threshold)
    low_cpu = NodeHealthMetrics(cpu_percent=60.0, is_online=True)
    controller.evaluate_metrics(low_cpu)
    
    # Mode successfully recovers to NORMAL
    assert controller.current_mode == RuntimeMode.NORMAL


def test_runtime_decisions_are_logged(controller):
    """All mode transitions append detailed audit records to decision_history."""
    offline_metrics = NodeHealthMetrics(is_online=False)
    controller.evaluate_metrics(offline_metrics)

    time.sleep(0.15)
    online_metrics = NodeHealthMetrics(is_online=True, cpu_percent=40.0)
    controller.evaluate_metrics(online_metrics)

    history = controller.decision_history
    assert len(history) >= 2
    assert history[0].previous_mode == RuntimeMode.NORMAL
    assert history[0].new_mode == RuntimeMode.OFFLINE
    assert "offline" in history[0].trigger_reason.lower()

    assert history[1].previous_mode == RuntimeMode.OFFLINE
    assert history[1].new_mode == RuntimeMode.NORMAL
    assert "recovered" in history[1].trigger_reason.lower()
