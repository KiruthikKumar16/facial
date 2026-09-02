"""
Comprehensive Failure-Injection Test Framework for Edge-to-Cloud Synchronization.

Simulates 16 real-world failure scenarios:
1. Internet Disconnection
2. Intermittent Connectivity (Jitter & Packet Loss)
3. High Latency (Slow Links)
4. Packet / Request Drop
5. HTTP 500 (Internal Server Error)
6. HTTP 429 (Rate Limit Throttling)
7. Backend Server Restart
8. PostgreSQL Database Disconnect / Restart
9. Edge Process Crash
10. Edge Machine Hard Reboot
11. Duplicate Event Submission
12. Out-of-Order Event Submission
13. Missing Event Sequence Range Gaps
14. SQLite Corruption & Recovery
15. Disk Space Exhaustion (Emergency Storage Pressure)
16. WebSocket Abrupt Disconnection & Reconnection
"""

from __future__ import annotations

import enum
import json
import logging
import os
import random
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FaultType(str, enum.Enum):
    NONE = "NONE"
    DISCONNECTED = "DISCONNECTED"
    INTERMITTENT = "INTERMITTENT"
    HIGH_LATENCY = "HIGH_LATENCY"
    PACKET_DROP = "PACKET_DROP"
    HTTP_500 = "HTTP_500"
    HTTP_429 = "HTTP_429"
    BACKEND_DOWN = "BACKEND_DOWN"
    DB_DOWN = "DB_DOWN"
    DISK_FULL = "DISK_FULL"
    WS_DISCONNECTED = "WS_DISCONNECTED"


@dataclass
class ScenarioResult:
    """Result and recovery audit metrics for a failure scenario."""
    scenario_id: int
    name: str
    events_generated: int
    events_persisted_edge: int
    events_received_backend: int
    duplicates_attempted: int
    duplicates_in_db: int  # Must be 0 (exactly-once effect)
    lost_events: int       # Must be 0
    recovery_time_ms: float
    critical_events_prioritized: bool
    consistency_verified: bool
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "events_generated": self.events_generated,
            "events_persisted_edge": self.events_persisted_edge,
            "events_received_backend": self.events_received_backend,
            "duplicates_attempted": self.duplicates_attempted,
            "duplicates_in_db": self.duplicates_in_db,
            "lost_events": self.lost_events,
            "recovery_time_ms": round(self.recovery_time_ms, 2),
            "critical_events_prioritized": self.critical_events_prioritized,
            "consistency_verified": self.consistency_verified,
            "details": self.details,
        }


class MockNetworkProxy:
    """Simulates network transport faults between edge and backend."""

    def __init__(self) -> None:
        self.fault: FaultType = FaultType.NONE
        self.latency_ms: float = 0.0
        self.packet_loss_rate: float = 0.0
        self.http_status_override: Optional[int] = None
        self.request_count: int = 0
        self.dropped_count: int = 0
        self.server_handler: Optional[Callable[[Dict[str, Any]], Tuple[int, Dict[str, Any]]]] = None

    def set_fault(
        self,
        fault: FaultType,
        latency_ms: float = 0.0,
        packet_loss_rate: float = 0.0,
        http_status: Optional[int] = None,
    ) -> None:
        self.fault = fault
        self.latency_ms = latency_ms
        self.packet_loss_rate = packet_loss_rate
        self.http_status_override = http_status

    def clear_faults(self) -> None:
        self.fault = FaultType.NONE
        self.latency_ms = 0.0
        self.packet_loss_rate = 0.0
        self.http_status_override = None

    def send_request(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Simulate HTTP request dispatch through configured fault conditions."""
        self.request_count += 1

        # 1. Total Disconnection / Backend Down
        if self.fault in (FaultType.DISCONNECTED, FaultType.BACKEND_DOWN):
            raise ConnectionError("Network unreachable / Connection refused")

        # 2. Intermittent Packet Loss
        if self.fault == FaultType.INTERMITTENT:
            if random.random() < (self.packet_loss_rate or 0.50):
                self.dropped_count += 1
                raise ConnectionResetError("Connection reset by peer (packet dropped)")

        # 3. Explicit Packet Drop
        if self.fault == FaultType.PACKET_DROP:
            self.dropped_count += 1
            raise TimeoutError("Request timed out (packet dropped in transit)")

        # 4. Injected Latency
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        # 5. HTTP 500 / 429 Overrides
        if self.fault == FaultType.HTTP_500 or self.http_status_override == 500:
            return 500, {"detail": "Internal Server Error (Simulated Fault)"}

        if self.fault == FaultType.HTTP_429 or self.http_status_override == 429:
            return 429, {"detail": "Too Many Requests (Rate limit exceeded)", "retry_after": 2}

        # 6. Dispatch to Mock Server Handler
        if self.server_handler:
            return self.server_handler(payload)

        return 200, {"status": "ok", "inserted": True}


class MockBackendServer:
    """Mock backend server maintaining database state and idempotency tracking."""

    def __init__(self) -> None:
        self.db_detections: Dict[str, Dict[str, Any]] = {}  # Key: event_id
        self.sequence_acks: Dict[str, int] = {}             # Key: camera_id -> last_seq
        self.db_online: bool = True
        self.ws_clients: List[str] = []

    def handle_detection(self, req: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        if not self.db_online:
            return 503, {"detail": "PostgreSQL database connection pool unavailable"}

        event_id = req["event_id"]
        camera_id = req["camera_id"]
        seq = req.get("sequence_number", 0)

        # Idempotency Check:
        if event_id in self.db_detections:
            return 200, {
                "id": self.db_detections[event_id]["id"],
                "event_id": event_id,
                "inserted": False,
                "sync_info": {
                    "is_duplicate": True,
                    "is_out_of_order": False,
                    "is_gap_detected": False,
                    "last_acknowledged_sequence": self.sequence_acks.get(camera_id, 0),
                }
            }

        # New event ingestion
        last_seq = self.sequence_acks.get(camera_id, 0)
        is_out_of_order = seq < last_seq
        is_gap = seq > (last_seq + 1)

        self.db_detections[event_id] = {
            "id": f"det_{len(self.db_detections) + 1}",
            "event_id": event_id,
            "camera_id": camera_id,
            "sequence_number": seq,
            "identity": req.get("identity", "Unknown"),
            "confidence": req.get("confidence", 0.0),
            "priority": req.get("priority", "normal"),
            "received_at": time.time(),
        }
        self.sequence_acks[camera_id] = max(last_seq, seq)

        return 200, {
            "id": self.db_detections[event_id]["id"],
            "event_id": event_id,
            "inserted": True,
            "sync_info": {
                "is_duplicate": False,
                "is_out_of_order": is_out_of_order,
                "is_gap_detected": is_gap,
                "last_acknowledged_sequence": self.sequence_acks[camera_id],
            }
        }


class MockEdgeNodeSyncWorker:
    """Edge synchronization worker with SQLite buffer, priority queue, and retry logic."""

    def __init__(self, db_path: Path, network_proxy: MockNetworkProxy) -> None:
        self.db_path = db_path
        self.proxy = network_proxy
        self.device_id = "edge-node-01"
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS local_events (
                event_id TEXT PRIMARY KEY,
                camera_id TEXT,
                sequence_number INTEGER,
                identity TEXT,
                confidence REAL,
                priority TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at REAL
            )
        """)
        conn.commit()
        conn.close()

    def buffer_event(
        self,
        event_id: str,
        camera_id: str,
        sequence_number: int,
        identity: str,
        confidence: float,
        priority: str = "normal",
    ) -> None:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("""
            INSERT OR REPLACE INTO local_events 
            (event_id, camera_id, sequence_number, identity, confidence, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """, (event_id, camera_id, sequence_number, identity, confidence, priority, time.time()))
        conn.commit()
        conn.close()

    def sync_pending(self) -> int:
        """
        Synchronize pending events prioritizing critical events (VIP, Watchlist, Alerts).
        Returns number of successfully confirmed events.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        cur = conn.cursor()
        # Prioritize: critical > high > normal > low
        cur.execute("""
            SELECT event_id, camera_id, sequence_number, identity, confidence, priority 
            FROM local_events 
            WHERE status = 'PENDING'
            ORDER BY CASE priority 
                WHEN 'critical' THEN 1 
                WHEN 'high' THEN 2 
                WHEN 'normal' THEN 3 
                ELSE 4 END ASC, sequence_number ASC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        synced_count = 0
        for r in rows:
            payload = {
                "event_id": r[0],
                "camera_id": r[1],
                "sequence_number": r[2],
                "identity": r[3],
                "confidence": r[4],
                "priority": r[5],
                "device_id": self.device_id,
            }
            try:
                status_code, resp = self.proxy.send_request(payload)
                if status_code == 200:
                    with sqlite3.connect(str(self.db_path), timeout=10.0) as update_conn:
                        update_conn.execute("UPDATE local_events SET status = 'CONFIRMED' WHERE event_id = ?", (r[0],))
                        update_conn.commit()
                    synced_count += 1
                elif status_code in (429, 500, 503):
                    # Backoff on server pressure
                    break
            except Exception as e:
                logger.error(f"Sync failed for event {r[0]}: {e}")
                break

        return synced_count
