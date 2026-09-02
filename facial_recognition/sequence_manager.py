"""
Per-device/per-camera monotonically increasing sequence number management.

Architecture:
    - Each (device_id, camera_id) pair maintains independent sequence counter
    - Sequences survive application restarts (persisted in SQLite)
    - Sequences persist transactionally with event creation
    - Cloud backend tracks last acknowledged sequence per (device_id, camera_id)
    
Features:
    ✓ Durable counters (SQLite persistence)
    ✓ Monotonic increases (no reuse)
    ✓ Per-device/camera isolation
    ✓ Transaction-safe creation
    ✓ Duplicate detection (same seq + device + camera = duplicate)
    ✓ Gap detection (missing sequence ranges)
    ✓ Out-of-order detection
    ✓ Thread-safe operations
    ✓ Restart recovery
    
Guarantees:
    - Same device + camera + timestamp + seq N → Always produces same event_id
    - Sequence N never reused for same device+camera (monotonic)
    - Sequence N+1 follows N (gaps detectable)
    - Events with same seq+device+camera are duplicates
"""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple, Optional, Set
import logging

logger = logging.getLogger(__name__)


@dataclass
class SequenceInfo:
    """Information about a sequence counter."""
    device_id: str
    camera_id: str
    current_sequence: int
    last_updated: datetime
    event_count: int = 0


@dataclass
class SequenceGap:
    """Represents missing sequence numbers."""
    start: int
    end: int
    count: int


@dataclass
class SequenceAnomaly:
    """Detected anomalies in sequence stream."""
    anomaly_type: str  # "duplicate", "gap", "out_of_order"
    device_id: str
    camera_id: str
    expected_sequence: Optional[int]
    received_sequence: int
    timestamp: datetime
    details: str


class SequenceManager:
    """
    Per-device/per-camera sequence number manager with durable persistence.
    
    Thread-safe, survives process restarts, detects anomalies.
    """

    def __init__(self, db_path: str = "facial_recognition.db", timeout: float = 10.0):
        """
        Initialize sequence manager.
        
        Args:
            db_path: Path to SQLite database
            timeout: Database lock timeout in seconds
        """
        self.db_path = Path(db_path)
        self.timeout = timeout
        
        # In-memory cache of sequence counters (device_id, camera_id) → sequence
        self._sequence_cache: Dict[Tuple[str, str], int] = {}
        self._cache_lock = threading.Lock()
        
        # Track anomalies for reporting
        self._anomalies: list[SequenceAnomaly] = []
        self._anomalies_lock = threading.Lock()
        
        self._init_db()
        self._load_cache_from_db()

    def _init_db(self) -> None:
        """Create sequence tracking tables if not exist."""
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Table: per-device/camera sequence counters
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sequence_counters (
                    device_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    current_sequence INTEGER NOT NULL DEFAULT 0,
                    last_updated TEXT NOT NULL,
                    event_count INTEGER DEFAULT 0,
                    PRIMARY KEY (device_id, camera_id)
                )
            """)
            
            # Table: sequence audit log for anomaly detection
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sequence_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    capture_timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,  -- "normal", "duplicate", "gap", "out_of_order"
                    expected_sequence INTEGER,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Indices for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sequence_counters_device_camera
                ON sequence_counters(device_id, camera_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sequence_audit_device_camera
                ON sequence_audit(device_id, camera_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sequence_audit_created_at
                ON sequence_audit(created_at)
            """)
            
            conn.commit()
            logger.debug(f"Sequence manager database initialized: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize sequence database: {e}")
            raise
        finally:
            conn.close()

    def _load_cache_from_db(self) -> None:
        """Load sequence counters from database into memory cache."""
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT device_id, camera_id, current_sequence FROM sequence_counters")
            rows = cursor.fetchall()
            
            with self._cache_lock:
                self._sequence_cache.clear()
                for row in rows:
                    key = (row["device_id"], row["camera_id"])
                    self._sequence_cache[key] = row["current_sequence"]
            
            if rows:
                logger.debug(f"Loaded {len(rows)} sequence counters from database")
        except sqlite3.Error as e:
            logger.error(f"Failed to load sequence cache from database: {e}")
            raise
        finally:
            conn.close()

    def get_next_sequence(self, device_id: str, camera_id: str) -> int:
        """
        Get the next sequence number for a device/camera pair.
        
        This increments the counter atomically and prepares for event creation.
        The sequence is committed to database only when event is persisted.
        
        Args:
            device_id: Device identifier
            camera_id: Camera identifier
            
        Returns:
            Next sequence number (1-indexed, monotonically increasing)
        """
        key = (device_id, camera_id)
        
        with self._cache_lock:
            current = self._sequence_cache.get(key, 0)
            next_seq = current + 1
            self._sequence_cache[key] = next_seq
        
        return next_seq

    def commit_sequence(
        self,
        device_id: str,
        camera_id: str,
        sequence_number: int,
        capture_timestamp: datetime,
        connection: Optional[sqlite3.Connection] = None,
    ) -> None:
        """
        Commit sequence number to database transactionally.
        
        This should be called within the same transaction as event creation.
        If called externally with a connection, uses that connection.
        Otherwise, opens a new connection.
        
        Args:
            device_id: Device identifier
            camera_id: Camera identifier
            sequence_number: Sequence number to commit
            capture_timestamp: Event capture timestamp
            connection: Optional existing database connection (for transactions)
        """
        should_close = False
        try:
            if connection is None:
                connection = sqlite3.connect(str(self.db_path), timeout=self.timeout)
                should_close = True
            
            cursor = connection.cursor()
            now = datetime.now(timezone.utc).isoformat()
            
            # Upsert: update if exists, insert if not
            cursor.execute("""
                INSERT INTO sequence_counters 
                    (device_id, camera_id, current_sequence, last_updated, event_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(device_id, camera_id) DO UPDATE SET
                    current_sequence = ?,
                    last_updated = ?,
                    event_count = event_count + 1
            """, (
                device_id, camera_id, sequence_number, now,
                sequence_number, now
            ))
            
            # Log to audit table
            cursor.execute("""
                INSERT INTO sequence_audit
                    (device_id, camera_id, sequence_number, capture_timestamp, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                device_id, camera_id, sequence_number, 
                capture_timestamp.isoformat(), "normal", now
            ))
            
            if should_close:
                connection.commit()
            
            with self._cache_lock:
                key = (device_id, camera_id)
                self._sequence_cache[key] = max(self._sequence_cache.get(key, 0), sequence_number)

            logger.debug(
                f"Committed sequence {sequence_number} for {device_id}/{camera_id}"
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to commit sequence: {e}")
            raise
        finally:
            if should_close and connection:
                connection.close()

    def detect_duplicate(
        self,
        device_id: str,
        camera_id: str,
        sequence_number: int,
        capture_timestamp: datetime,
        connection: Optional[sqlite3.Connection] = None,
    ) -> bool:
        """
        Detect if a sequence number has already been used for this device/camera.
        
        Args:
            device_id: Device identifier
            camera_id: Camera identifier
            sequence_number: Sequence number to check
            capture_timestamp: Event capture timestamp
            connection: Optional database connection
            
        Returns:
            True if this is a duplicate, False if new
        """
        should_close = False
        try:
            if connection is None:
                connection = sqlite3.connect(str(self.db_path), timeout=self.timeout)
                connection.row_factory = sqlite3.Row
                should_close = True
            
            cursor = connection.cursor()
            
            # Check if sequence already exists in audit log
            cursor.execute("""
                SELECT COUNT(*) as count FROM sequence_audit
                WHERE device_id = ? AND camera_id = ? AND sequence_number = ?
            """, (device_id, camera_id, sequence_number))
            
            result = cursor.fetchone()
            is_duplicate = result["count"] > 0
            
            if is_duplicate:
                self._record_anomaly(
                    device_id, camera_id, sequence_number,
                    capture_timestamp, "duplicate",
                    expected=None,
                    details=f"Sequence {sequence_number} already exists"
                )
            
            return is_duplicate
        except sqlite3.Error as e:
            logger.error(f"Failed to detect duplicate: {e}")
            raise
        finally:
            if should_close and connection:
                connection.close()

    def detect_gaps(
        self,
        device_id: str,
        camera_id: str,
        up_to_sequence: Optional[int] = None,
    ) -> list[SequenceGap]:
        """
        Detect missing sequence numbers in the audit log.
        
        Args:
            device_id: Device identifier
            camera_id: Camera identifier
            up_to_sequence: Only check up to this sequence (default: max observed)
            
        Returns:
            List of SequenceGap objects representing gaps
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all observed sequences
            cursor.execute("""
                SELECT DISTINCT sequence_number FROM sequence_audit
                WHERE device_id = ? AND camera_id = ?
                ORDER BY sequence_number ASC
            """, (device_id, camera_id))
            
            sequences = [row["sequence_number"] for row in cursor.fetchall()]
            
            if not sequences:
                return []
            
            # Find gaps
            gaps = []
            for i in range(len(sequences) - 1):
                current = sequences[i]
                next_expected = current + 1
                next_actual = sequences[i + 1]
                
                if next_actual > next_expected:
                    gap = SequenceGap(
                        start=next_expected,
                        end=next_actual - 1,
                        count=next_actual - next_expected
                    )
                    gaps.append(gap)
            
            return gaps
        except sqlite3.Error as e:
            logger.error(f"Failed to detect gaps: {e}")
            raise
        finally:
            conn.close()

    def detect_out_of_order(
        self,
        device_id: str,
        camera_id: str,
        sequence_number: int,
        capture_timestamp: datetime,
        connection: Optional[sqlite3.Connection] = None,
    ) -> bool:
        """
        Detect if this sequence arrived out of order.
        
        Args:
            device_id: Device identifier
            camera_id: Camera identifier
            sequence_number: Arriving sequence number
            capture_timestamp: Event capture timestamp
            connection: Optional database connection
            
        Returns:
            True if out of order (sequence < max observed), False if in order
        """
        should_close = False
        try:
            if connection is None:
                connection = sqlite3.connect(str(self.db_path), timeout=self.timeout)
                connection.row_factory = sqlite3.Row
                should_close = True
            
            cursor = connection.cursor()
            
            # Get max sequence observed so far
            cursor.execute("""
                SELECT MAX(sequence_number) as max_seq FROM sequence_audit
                WHERE device_id = ? AND camera_id = ?
            """, (device_id, camera_id))
            
            result = cursor.fetchone()
            max_seq = result["max_seq"] if result["max_seq"] is not None else 0
            
            is_out_of_order = sequence_number <= max_seq
            
            if is_out_of_order:
                self._record_anomaly(
                    device_id, camera_id, sequence_number,
                    capture_timestamp, "out_of_order",
                    expected=max_seq + 1,
                    details=f"Sequence {sequence_number} arrived after {max_seq}"
                )
            
            return is_out_of_order
        except sqlite3.Error as e:
            logger.error(f"Failed to detect out-of-order: {e}")
            raise
        finally:
            if should_close and connection:
                connection.close()

    def get_sequence_info(
        self,
        device_id: str,
        camera_id: str,
    ) -> Optional[SequenceInfo]:
        """
        Get current sequence information for a device/camera.
        
        Args:
            device_id: Device identifier
            camera_id: Camera identifier
            
        Returns:
            SequenceInfo object or None if no sequences recorded
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM sequence_counters
                WHERE device_id = ? AND camera_id = ?
            """, (device_id, camera_id))
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return SequenceInfo(
                device_id=row["device_id"],
                camera_id=row["camera_id"],
                current_sequence=row["current_sequence"],
                last_updated=datetime.fromisoformat(row["last_updated"]),
                event_count=row["event_count"],
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to get sequence info: {e}")
            raise
        finally:
            conn.close()

    def get_all_sequence_info(self) -> list[SequenceInfo]:
        """
        Get sequence information for all device/camera pairs.
        
        Returns:
            List of SequenceInfo objects
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM sequence_counters ORDER BY device_id, camera_id")
            rows = cursor.fetchall()
            
            return [
                SequenceInfo(
                    device_id=row["device_id"],
                    camera_id=row["camera_id"],
                    current_sequence=row["current_sequence"],
                    last_updated=datetime.fromisoformat(row["last_updated"]),
                    event_count=row["event_count"],
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all sequence info: {e}")
            raise
        finally:
            conn.close()

    def get_anomalies(
        self,
        device_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        anomaly_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[SequenceAnomaly]:
        """
        Get recorded anomalies.
        
        Args:
            device_id: Filter by device (optional)
            camera_id: Filter by camera (optional)
            anomaly_type: Filter by type (optional)
            limit: Maximum number of results
            
        Returns:
            List of SequenceAnomaly objects
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM sequence_audit WHERE status IN ('duplicate', 'gap', 'out_of_order')"
            params = []
            
            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)
            
            if camera_id:
                query += " AND camera_id = ?"
                params.append(camera_id)
            
            if anomaly_type:
                query += " AND status = ?"
                params.append(anomaly_type)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                SequenceAnomaly(
                    anomaly_type=row["status"],
                    device_id=row["device_id"],
                    camera_id=row["camera_id"],
                    expected_sequence=row["expected_sequence"],
                    received_sequence=row["sequence_number"],
                    timestamp=datetime.fromisoformat(row["created_at"]),
                    details=f"Sequence {row['sequence_number']}",
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get anomalies: {e}")
            raise
        finally:
            conn.close()

    def _record_anomaly(
        self,
        device_id: str,
        camera_id: str,
        sequence_number: int,
        capture_timestamp: datetime,
        anomaly_type: str,
        expected: Optional[int] = None,
        details: str = "",
    ) -> None:
        """
        Record an anomaly in the audit log.
        
        Args:
            device_id: Device identifier
            camera_id: Camera identifier
            sequence_number: Sequence number involved
            capture_timestamp: Event timestamp
            anomaly_type: Type of anomaly
            expected: Expected sequence (for out-of-order/gap)
            details: Additional details
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            
            cursor.execute("""
                INSERT INTO sequence_audit
                    (device_id, camera_id, sequence_number, capture_timestamp, 
                     status, expected_sequence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, camera_id, sequence_number,
                capture_timestamp.isoformat(), anomaly_type,
                expected, now
            ))
            
            conn.commit()
            
            logger.warning(
                f"Sequence anomaly: {anomaly_type} for {device_id}/{camera_id} "
                f"seq={sequence_number} ({details})"
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to record anomaly: {e}")
        finally:
            conn.close()

    def reset_for_testing(self) -> None:
        """Reset all sequence data (for testing only)."""
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM sequence_counters")
            cursor.execute("DELETE FROM sequence_audit")
            
            conn.commit()
            
            with self._cache_lock:
                self._sequence_cache.clear()
            
            logger.info("Sequence data reset (testing only)")
        except sqlite3.Error as e:
            logger.error(f"Failed to reset sequence data: {e}")
            raise
        finally:
            conn.close()
