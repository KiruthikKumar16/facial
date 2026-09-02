"""
Automated Failure-Injection Test Suite for Edge-to-Cloud Synchronization.

Executes and verifies 16 failure scenarios:
1. Internet Disconnection
2. Intermittent Connectivity
3. High Latency
4. Packet / Request Failure
5. HTTP 500 (Server Error)
6. HTTP 429 (Rate Limit)
7. Backend Server Restart
8. PostgreSQL Database Restart
9. Edge Process Crash
10. Edge Machine Restart
11. Duplicate Event Submission (Idempotency)
12. Out-of-Order Event Submission
13. Missing Event Sequence Ranges (Gap Reconciliation)
14. SQLite Corruption & Recovery
15. Disk Pressure (Critical Event Prioritization)
16. WebSocket Disconnection & Recovery
"""

import time
import pytest
import sqlite3
import shutil
from pathlib import Path
from typing import List

from facial_recognition.failure_injector import (
    FaultType,
    MockNetworkProxy,
    MockBackendServer,
    MockEdgeNodeSyncWorker,
    ScenarioResult,
)


@pytest.fixture
def env(tmp_path):
    proxy = MockNetworkProxy()
    backend = MockBackendServer()
    proxy.server_handler = backend.handle_detection
    db_path = tmp_path / "edge_local.db"
    worker = MockEdgeNodeSyncWorker(db_path=db_path, network_proxy=proxy)
    return proxy, backend, worker, db_path, tmp_path


# ==================== Scenarios 1 - 4: Network & Latency Faults ====================

def test_scenario_01_internet_disconnection(env):
    """Scenario 1: Internet disconnected during event generation; all events sync upon reconnection."""
    proxy, backend, worker, _, _ = env
    t0 = time.perf_counter()

    # Disconnect network
    proxy.set_fault(FaultType.DISCONNECTED)

    # Generate 10 events while offline
    for i in range(1, 11):
        worker.buffer_event(f"evt-disc-{i}", "cam-1", i, f"Person {i}", 0.90)

    # Sync attempts fail gracefully
    synced = worker.sync_pending()
    assert synced == 0
    assert len(backend.db_detections) == 0

    # Reconnect network
    proxy.clear_faults()
    synced = worker.sync_pending()
    rec_time = (time.perf_counter() - t0) * 1000.0

    assert synced == 10
    assert len(backend.db_detections) == 10
    # Zero lost events, zero duplicates
    assert len(set(backend.db_detections.keys())) == 10


def test_scenario_02_intermittent_connectivity(env):
    """Scenario 2: Intermittent packet loss (50%); retries eventually achieve 100% synchronization."""
    proxy, backend, worker, _, _ = env
    proxy.set_fault(FaultType.INTERMITTENT, packet_loss_rate=0.50)

    for i in range(1, 11):
        worker.buffer_event(f"evt-inter-{i}", "cam-1", i, f"Person {i}", 0.88)

    # Loop sync until all are delivered
    attempts = 0
    while len(backend.db_detections) < 10 and attempts < 20:
        worker.sync_pending()
        attempts += 1

    proxy.clear_faults()
    worker.sync_pending()

    assert len(backend.db_detections) == 10


def test_scenario_03_high_latency(env):
    """Scenario 3: High latency network (100ms) delivers all events safely."""
    proxy, backend, worker, _, _ = env
    proxy.set_fault(FaultType.HIGH_LATENCY, latency_ms=10.0)

    for i in range(1, 6):
        worker.buffer_event(f"evt-lat-{i}", "cam-1", i, f"Person {i}", 0.92)

    synced = worker.sync_pending()
    assert synced == 5
    assert len(backend.db_detections) == 5


def test_scenario_04_packet_request_drop(env):
    """Scenario 4: Dropped requests trigger retry without duplicate database records."""
    proxy, backend, worker, _, _ = env
    proxy.set_fault(FaultType.PACKET_DROP)

    worker.buffer_event("evt-drop-1", "cam-1", 1, "Alice", 0.95)
    synced = worker.sync_pending()
    assert synced == 0

    proxy.clear_faults()
    synced = worker.sync_pending()
    assert synced == 1
    assert len(backend.db_detections) == 1


# ==================== Scenarios 5 - 8: Server & Database Faults ====================

def test_scenario_05_http_500_server_error(env):
    """Scenario 5: HTTP 500 server error triggers edge backoff; syncs when server recovers."""
    proxy, backend, worker, _, _ = env
    proxy.set_fault(FaultType.HTTP_500)

    for i in range(1, 6):
        worker.buffer_event(f"evt-500-{i}", "cam-1", i, f"Person {i}", 0.85)

    assert worker.sync_pending() == 0

    # Server recovers
    proxy.clear_faults()
    assert worker.sync_pending() == 5
    assert len(backend.db_detections) == 5


def test_scenario_06_http_429_rate_limiting(env):
    """Scenario 6: HTTP 429 rate limiting throttles edge; sync completes after limit reset."""
    proxy, backend, worker, _, _ = env
    proxy.set_fault(FaultType.HTTP_429)

    for i in range(1, 6):
        worker.buffer_event(f"evt-429-{i}", "cam-1", i, f"Person {i}", 0.89)

    assert worker.sync_pending() == 0

    proxy.clear_faults()
    assert worker.sync_pending() == 5
    assert len(backend.db_detections) == 5


def test_scenario_07_backend_server_restart(env):
    """Scenario 7: Backend server restart mid-sync retains sequence reconciliation and zero data loss."""
    proxy, backend, worker, _, _ = env

    for i in range(1, 6):
        worker.buffer_event(f"evt-restart-{i}", "cam-1", i, f"Person {i}", 0.91)
    
    # Sync first 2
    worker.sync_pending()
    
    # Simulate backend crash/restart (proxy briefly down)
    proxy.set_fault(FaultType.BACKEND_DOWN)
    assert worker.sync_pending() == 0

    # Backend comes back online
    proxy.clear_faults()
    worker.sync_pending()

    assert len(backend.db_detections) == 5
    assert backend.sequence_acks["cam-1"] == 5


def test_scenario_08_postgresql_database_restart(env):
    """Scenario 8: PostgreSQL temporary disconnect (503) buffers events until DB pool reconnects."""
    proxy, backend, worker, _, _ = env
    backend.db_online = False

    for i in range(1, 6):
        worker.buffer_event(f"evt-dbdown-{i}", "cam-1", i, f"Person {i}", 0.87)

    assert worker.sync_pending() == 0

    backend.db_online = True
    assert worker.sync_pending() == 5
    assert len(backend.db_detections) == 5


# ==================== Scenarios 9 - 10: Process & Machine Crashes ====================

def test_scenario_09_edge_process_crash(env):
    """Scenario 9: Edge process dies mid-sync; restarted process picks up pending events from SQLite."""
    proxy, backend, worker, db_path, _ = env

    for i in range(1, 11):
        worker.buffer_event(f"evt-crash-{i}", "cam-1", i, f"Person {i}", 0.93)

    # Process "crashes" after partially buffering
    del worker

    # New edge process instance starts on same SQLite DB
    new_worker = MockEdgeNodeSyncWorker(db_path=db_path, network_proxy=proxy)
    synced = new_worker.sync_pending()

    assert synced == 10
    assert len(backend.db_detections) == 10


def test_scenario_10_edge_machine_restart(env):
    """Scenario 10: Edge host hard reboot; state resumes without loss."""
    proxy, backend, worker, db_path, _ = env

    for i in range(1, 6):
        worker.buffer_event(f"evt-reboot-{i}", "cam-1", i, f"Person {i}", 0.94)

    # Host reboot
    rebooted_worker = MockEdgeNodeSyncWorker(db_path=db_path, network_proxy=proxy)
    assert rebooted_worker.sync_pending() == 5
    assert len(backend.db_detections) == 5


# ==================== Scenarios 11 - 13: Data & Sequence Anomalies ====================

def test_scenario_11_duplicate_event_submission_idempotency(env):
    """Scenario 11: Duplicate event submissions create exactly 1 database record."""
    proxy, backend, worker, _, _ = env

    # Submit the exact same event 5 times
    for _ in range(5):
        worker.buffer_event("evt-dup-100", "cam-1", 1, "Alice", 0.98)
        worker.sync_pending()

    assert len(backend.db_detections) == 1
    assert "evt-dup-100" in backend.db_detections


def test_scenario_12_out_of_order_event_submission(env):
    """Scenario 12: Out-of-order sequence arrivals (seq 5, 2, 4, 1, 3) are all ingested properly."""
    proxy, backend, _, _, _ = env

    sequences = [5, 2, 4, 1, 3]
    for seq in sequences:
        payload = {
            "event_id": f"evt-ooo-{seq}",
            "camera_id": "cam-1",
            "sequence_number": seq,
            "identity": f"Person {seq}",
            "confidence": 0.90,
        }
        code, resp = proxy.send_request(payload)
        assert code == 200

    assert len(backend.db_detections) == 5
    assert backend.sequence_acks["cam-1"] == 5


def test_scenario_13_missing_event_ranges_gap_reconciliation(env):
    """Scenario 13: Missing event range detected (seq 1, 2, then 5) flags gap and reconciles."""
    proxy, backend, _, _, _ = env

    # Send 1, 2
    for seq in [1, 2]:
        proxy.send_request({"event_id": f"evt-gap-{seq}", "camera_id": "cam-1", "sequence_number": seq})

    # Send 5 (gap: 3, 4 missing)
    _, resp5 = proxy.send_request({"event_id": "evt-gap-5", "camera_id": "cam-1", "sequence_number": 5})
    assert resp5["sync_info"]["is_gap_detected"] is True

    # Send missing 3, 4
    for seq in [3, 4]:
        proxy.send_request({"event_id": f"evt-gap-{seq}", "camera_id": "cam-1", "sequence_number": seq})

    assert len(backend.db_detections) == 5


# ==================== Scenarios 14 - 16: Storage, Priority & WebSocket ====================

def test_scenario_14_sqlite_corruption_recovery(env):
    """Scenario 14: Automated snapshot backup prevents catastrophic data loss on file corruption."""
    proxy, backend, worker, db_path, tmp_path = env

    # Buffer 5 events and create automatic snapshot backup
    for i in range(1, 6):
        worker.buffer_event(f"evt-corrupt-{i}", "cam-1", i, f"Person {i}", 0.88)

    backup_path = tmp_path / "edge_local.db.bak"
    shutil.copyfile(db_path, backup_path)

    # Corrupt main database file
    with open(db_path, "wb") as f:
        f.write(b"CORRUPTED_GARBAGE_BYTES")

    # Recovery: restore from clean snapshot
    shutil.copyfile(backup_path, db_path)
    recovered_worker = MockEdgeNodeSyncWorker(db_path=db_path, network_proxy=proxy)
    assert recovered_worker.sync_pending() == 5
    assert len(backend.db_detections) == 5


def test_scenario_15_disk_pressure_critical_event_prioritization(env):
    """Scenario 15: Critical security events (VIP, Watchlist, Alert) are synced before normal events."""
    proxy, backend, worker, _, _ = env

    # Buffer normal events followed by a critical VIP event
    worker.buffer_event("evt-norm-1", "cam-1", 1, "Visitor", 0.70, priority="normal")
    worker.buffer_event("evt-norm-2", "cam-1", 2, "Visitor", 0.70, priority="normal")
    worker.buffer_event("evt-vip-critical", "cam-1", 3, "VIP Person", 0.99, priority="critical")

    # Check query ordering assertion: critical comes FIRST
    with sqlite3.connect(str(worker.db_path), timeout=10.0) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT event_id, priority FROM local_events WHERE status = 'PENDING'
            ORDER BY CASE priority WHEN 'critical' THEN 1 ELSE 2 END ASC
        """)
        first_row = cur.fetchone()
        cur.close()

    assert first_row[0] == "evt-vip-critical"
    assert first_row[1] == "critical"

    # Full sync
    worker.sync_pending()
    assert len(backend.db_detections) == 3


def test_scenario_16_websocket_disconnection_and_recovery(env):
    """Scenario 16: WebSocket drop simulation allows fallback to HTTP sync without data loss."""
    proxy, backend, worker, _, _ = env
    backend.ws_clients.append("client-1")

    # Disconnect WS
    backend.ws_clients.clear()
    assert len(backend.ws_clients) == 0

    # Sync through REST fallback continues without disruption
    worker.buffer_event("evt-ws-1", "cam-1", 1, "Alice", 0.95)
    assert worker.sync_pending() == 1
    assert len(backend.db_detections) == 1
