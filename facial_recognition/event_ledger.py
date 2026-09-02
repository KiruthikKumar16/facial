"""
Offline-first transactional event ledger using SQLite.

Provides:
- Atomic event persistence before cloud transmission
- Transaction log with sequence numbers for replay/recovery
- Efficient sync queue for reliable cloud transmission
- Device state tracking
- Migration utilities for existing CSV files
- WAL mode for concurrent read/write
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

try:
    from .deterministic_event_id import generate_event_id
    from .sequence_manager import SequenceManager, SequenceAnomaly, SequenceGap
    from .integrity import EventHasher
except ImportError:
    from deterministic_event_id import generate_event_id
    from sequence_manager import SequenceManager, SequenceAnomaly, SequenceGap
    from integrity import EventHasher

logger = logging.getLogger(__name__)


class EventLedger:
    """Thread-safe SQLite-based event ledger for facial recognition events."""

    # SQL table definitions
    SCHEMA = [
        """
        CREATE TABLE IF NOT EXISTS recognition_events (
            event_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            camera_id TEXT NOT NULL,
            sequence_number INTEGER NOT NULL,
            capture_timestamp TEXT NOT NULL,
            identity TEXT,
            confidence REAL,
            embedding_vector BLOB,
            model_version TEXT,
            event_payload TEXT,
            age INTEGER,
            gender TEXT,
            created_at TEXT NOT NULL,
            sync_status TEXT NOT NULL DEFAULT 'CREATED',
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            last_retry_at TEXT,
            next_retry_at TEXT,
            sync_timestamp TEXT,
            dedup_key TEXT,
            config_version INTEGER DEFAULT 1,
            event_hash TEXT NOT NULL,
            previous_event_hash TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_event_id 
        ON recognition_events(event_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_sequence_number 
        ON recognition_events(sequence_number)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_sync_status 
        ON recognition_events(sync_status)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_next_retry_at 
        ON recognition_events(next_retry_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_capture_timestamp 
        ON recognition_events(capture_timestamp)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_camera_id 
        ON recognition_events(camera_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_device_id 
        ON recognition_events(device_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recognition_events_dedup_key 
        ON recognition_events(dedup_key, capture_timestamp)
        """,
        """
        CREATE TABLE IF NOT EXISTS sync_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES recognition_events(event_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_sync_queue_priority_created 
        ON sync_queue(priority DESC, created_at ASC)
        """,
        """
        CREATE TABLE IF NOT EXISTS sync_state_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            from_state TEXT,
            to_state TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES recognition_events(event_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_sync_state_transitions_event_id 
        ON sync_state_transitions(event_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS device_state (
            device_id TEXT PRIMARY KEY,
            last_heartbeat TEXT,
            last_successful_sync TEXT,
            pending_event_count INTEGER DEFAULT 0,
            synced_event_count INTEGER DEFAULT 0,
            failed_event_count INTEGER DEFAULT 0,
            last_updated TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS migration_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            event_count INTEGER,
            migrated_at TEXT,
            status TEXT
        )
        """,
    ]

    def __init__(
        self,
        db_path: str = "facial_recognition.db",
        device_id: Optional[str] = None,
        enable_wal: bool = True,
        timeout: float = 10.0,
    ):
        """
        Initialize the event ledger.

        Args:
            db_path: Path to SQLite database file
            device_id: Unique device identifier (default: hostname)
            enable_wal: Enable Write-Ahead Logging for better concurrency
            timeout: Database lock timeout in seconds
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.device_id = device_id or os.environ.get("DEVICE_ID") or self._get_device_id()
        self.timeout = timeout
        self.enable_wal = enable_wal
        
        self._local = threading.local()
        self._sequence_counter = 0
        self._counter_lock = threading.Lock()
        
        # Initialize per-device/camera sequence manager
        self.sequence_manager = SequenceManager(db_path=str(db_path), timeout=timeout)
        
        self._init_db()
        
        # Verify schema for migration
        self._migrate_schema()
        
        # Ensure device_state row exists immediately so tests and reads don't need add_event first
        self._ensure_device_state()


    def _get_device_id(self) -> str:
        """Generate device ID from hostname or environment."""
        try:
            return os.environ.get("DEVICE_ID") or __import__("socket").gethostname()
        except Exception:
            return "edge-node-default"

    def _init_db(self) -> None:
        """Initialize database schema and settings."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Enable WAL mode for better concurrency
            if self.enable_wal:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            else:
                cursor.execute("PRAGMA synchronous=FULL")
            
            # Performance settings
            cursor.execute("PRAGMA cache_size=10000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA query_only=FALSE")
            
            # Create tables
            for schema_sql in self.SCHEMA:
                cursor.execute(schema_sql)
            
            conn.commit()
            logger.info(f"EventLedger initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                timeout=self.timeout,
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _get_next_sequence(self) -> int:
        """Get next sequence number (monotonically increasing)."""
        with self._counter_lock:
            self._sequence_counter += 1
            return self._sequence_counter

    def _ensure_device_state(self) -> None:
        """Ensure device state record exists (race-safe via INSERT OR IGNORE)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO device_state 
                (device_id, last_updated, pending_event_count, synced_event_count, failed_event_count)
                VALUES (?, ?, 0, 0, 0)
                """,
                (self.device_id, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to ensure device state: {e}")
            raise

    def _migrate_schema(self) -> None:
        """Add new columns to existing schema gracefully."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(recognition_events)")
            columns = [info[1] for info in cursor.fetchall()]
            
            migrated = False
            if "event_hash" not in columns:
                cursor.execute("ALTER TABLE recognition_events ADD COLUMN event_hash TEXT DEFAULT 'LEGACY_UNHASHED'")
                migrated = True
            if "previous_event_hash" not in columns:
                cursor.execute("ALTER TABLE recognition_events ADD COLUMN previous_event_hash TEXT DEFAULT 'LEGACY_UNHASHED'")
                migrated = True
            if "config_version" not in columns:
                cursor.execute("ALTER TABLE recognition_events ADD COLUMN config_version INTEGER DEFAULT 1")
                migrated = True
                
            if migrated:
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to reset event sequences: {e}")
            conn.rollback()
            return 0

    def verify_ledger_integrity(self, camera_id: str) -> Dict[str, Any]:
        """
        Verify the cryptographic integrity of the event chain for a specific camera.
        
        This detects modifications to payloads, hashes, and chain order.
        
        Returns:
            Dict containing:
                - is_valid: bool
                - events_verified: int
                - error: Optional string describing the failure point
                - failed_sequence: Optional int indicating where the chain broke
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT 
                event_id, device_id, camera_id, sequence_number, capture_timestamp, 
                identity, confidence, event_payload, age, gender, 
                event_hash, previous_event_hash, config_version
            FROM recognition_events 
            WHERE camera_id = ? 
            ORDER BY sequence_number ASC
            """,
            (camera_id,)
        )
        
        rows = cursor.fetchall()
        
        if not rows:
            return {"is_valid": True, "events_verified": 0, "error": None, "failed_sequence": None}
            
        expected_previous = EventHasher.GENESIS_HASH
        events_verified = 0
        
        for row in rows:
            (event_id, device_id, cam_id, seq, timestamp, 
             identity, confidence, payload, age, gender, 
             stored_hash, stored_prev_hash, conf_ver) = row
             
            # Ignore legacy unhashed rows from migration
            if stored_hash == "LEGACY_UNHASHED":
                continue
                
            # 1. Verify chain continuity
            if stored_prev_hash != expected_previous:
                return {
                    "is_valid": False, 
                    "events_verified": events_verified, 
                    "error": f"Chain broken: Expected prev hash {expected_previous}, found {stored_prev_hash}", 
                    "failed_sequence": seq
                }
                
            # 2. Verify payload hash math
            calculated_hash = EventHasher.compute_hash(
                event_id=event_id,
                device_id=device_id,
                camera_id=cam_id,
                sequence_number=seq,
                capture_timestamp=timestamp,
                identity=identity,
                confidence=confidence,
                event_payload=payload,
                age=age,
                gender=gender,
                previous_event_hash=stored_prev_hash,
                config_version=conf_ver or 1
            )
            
            if calculated_hash != stored_hash:
                return {
                    "is_valid": False, 
                    "events_verified": events_verified, 
                    "error": f"Data tampered: Calculated hash {calculated_hash} does not match stored {stored_hash}", 
                    "failed_sequence": seq
                }
                
            expected_previous = stored_hash
            events_verified += 1
            
        return {"is_valid": True, "events_verified": events_verified, "error": None, "failed_sequence": None}

    def add_event(
        self,
        camera_id: str,
        identity: Optional[str] = None,
        confidence: float = 0.0,
        embedding: Optional[bytes] = None,
        model_version: Optional[str] = None,
        age: Optional[int] = None,
        gender: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
        dedup_key: Optional[str] = None,
        capture_timestamp: Optional[datetime] = None,
        priority: int = 10,
        config_version: Optional[int] = 1,
    ) -> str:
        """
        Add a recognition event to the ledger.

        The event is persisted transactionally before returning.
        This function is synchronous and blocks until the event is safely stored.

        Args:
            camera_id: Camera identifier
            identity: Recognized person name (or "Unknown"/"Person N")
            confidence: Recognition confidence (0.0-1.0)
            embedding: Face embedding as numpy array or bytes
            model_version: Model/algorithm version
            age: Estimated age
            gender: Estimated gender
            event_payload: Additional event data as dict
            dedup_key: Key for deduplication (camera_id, identity tuple)
            capture_timestamp: Optional event capture time (for deterministic event_id).
                             If provided, uses this instead of current time.
                             This ensures idempotency across retries.
            priority: Queue priority level (lower value = higher priority)

        Returns:
            event_id: Unique event identifier (deterministic, SHA-256 hash)

        Raises:
            sqlite3.Error: On database errors
        """
        self._ensure_device_state()
        
        # Use provided timestamp (for determinism) or fall back to current time
        if capture_timestamp is None:
            capture_timestamp = datetime.now(timezone.utc)
        elif capture_timestamp.tzinfo is None:
            # Assume UTC if no timezone
            capture_timestamp = capture_timestamp.replace(tzinfo=timezone.utc)
        
        # Get next sequence number for this device/camera pair
        sequence = self.sequence_manager.get_next_sequence(self.device_id, camera_id)
        
        # Generate deterministic event_id (SHA-256 hash)
        # This ensures idempotency: same event → same event_id
        event_id = generate_event_id(
            device_id=self.device_id,
            camera_id=camera_id,
            capture_timestamp=capture_timestamp,
            sequence_number=sequence,
            track_id=event_payload.get("track_id") if event_payload else None,
        )
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Serialize event payload
            payload_json = json.dumps(event_payload or {})
            now = datetime.now(timezone.utc)
            
            # Start transaction
            cursor.execute("BEGIN IMMEDIATE")
            
            # Fetch previous event hash for this camera
            cursor.execute(
                """
                SELECT event_hash FROM recognition_events 
                WHERE camera_id = ? 
                ORDER BY sequence_number DESC LIMIT 1
                """, 
                (camera_id,)
            )
            row = cursor.fetchone()
            previous_hash = row[0] if row else EventHasher.GENESIS_HASH

            # Calculate event hash
            event_hash = EventHasher.compute_hash(
                event_id=event_id,
                device_id=self.device_id,
                camera_id=camera_id,
                sequence_number=sequence,
                capture_timestamp=capture_timestamp.isoformat(),
                identity=identity,
                confidence=confidence,
                event_payload=payload_json,
                age=age,
                gender=gender,
                previous_event_hash=previous_hash,
                config_version=config_version or 1
            )
            
            # Insert event (use capture_timestamp for deterministic hashing)
            cursor.execute(
                """
                INSERT INTO recognition_events 
                (event_id, device_id, camera_id, sequence_number, capture_timestamp, 
                 identity, confidence, embedding_vector, model_version, event_payload,
                 age, gender, created_at, sync_status, dedup_key, config_version, event_hash, previous_event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    self.device_id,
                    camera_id,
                    sequence,
                    capture_timestamp.isoformat(),
                    identity,
                    confidence,
                    embedding,
                    model_version,
                    payload_json,
                    age,
                    gender,
                    now.isoformat(),
                    "STORED",
                    dedup_key,
                    config_version or 1,
                    event_hash,
                    previous_hash
                )
            )
            
            # Log transition CREATED -> STORED
            cursor.execute(
                """
                INSERT INTO sync_state_transitions (event_id, from_state, to_state, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, "CREATED", "STORED", "Initial persistence", now.isoformat())
            )
            
            # Transition to QUEUED
            cursor.execute(
                """
                UPDATE recognition_events 
                SET sync_status = 'QUEUED'
                WHERE event_id = ?
                """,
                (event_id,)
            )
            
            cursor.execute(
                """
                INSERT INTO sync_state_transitions (event_id, from_state, to_state, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, "STORED", "QUEUED", "Enqueued for sync", now.isoformat())
            )

            # Add to sync queue
            cursor.execute(
                """
                INSERT INTO sync_queue (event_id, priority, created_at)
                VALUES (?, ?, ?)
                """,
                (event_id, priority, now.isoformat())
            )
            
            # Commit transaction
            conn.commit()
            
            # Now persist sequence to sequence_manager (after transaction success)
            self.sequence_manager.commit_sequence(
                self.device_id, camera_id, sequence, capture_timestamp
            )
            
            logger.debug(f"Event {event_id} persisted (device={self.device_id}, camera={camera_id}, seq={sequence})")
            return event_id
            
        except sqlite3.IntegrityError as e:
            conn.rollback()
            logger.error(f"Integrity error adding event: {e}")
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add event: {e}")
            raise

    def get_pending_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch pending events ready for cloud sync.

        Returns events in priority and creation time order.

        Args:
            limit: Maximum events to return

        Returns:
            List of event dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT e.*, q.priority as queue_priority 
                FROM recognition_events e
                LEFT JOIN sync_queue q ON e.event_id = q.event_id
                WHERE e.sync_status = 'QUEUED' OR (e.sync_status = 'RETRYING' AND (e.next_retry_at IS NULL OR e.next_retry_at <= ?))
                ORDER BY q.priority DESC, e.created_at ASC
                LIMIT ?
                """,
                (datetime.now(timezone.utc).isoformat(), limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch pending events: {e}")
            return []

    def transition_state(
        self,
        event_id: str,
        to_state: str,
        reason: Optional[str] = None,
        increment_retry: bool = False,
        next_retry_at: Optional[str] = None
    ) -> bool:
        """
        Transition an event to a new state explicitly.
        
        Args:
            event_id: Event identifier
            to_state: New state (QUEUED, SENDING, ACKNOWLEDGED, COMPLETED, FAILED, RETRYING)
            reason: Optional reason or error message
            increment_retry: Whether to increment retry count
            next_retry_at: ISO formatted timestamp for next retry attempt (used for RETRYING)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            
            cursor.execute("BEGIN IMMEDIATE")
            
            # Get current state
            cursor.execute("SELECT sync_status FROM recognition_events WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return False
            
            from_state = row["sync_status"]
            
            # Update state
            update_sql = "UPDATE recognition_events SET sync_status = ?, error_message = ?"
            params = [to_state, reason]
            
            if increment_retry:
                update_sql += ", retry_count = retry_count + 1, last_retry_at = ?"
                params.append(now)
                
            if next_retry_at:
                update_sql += ", next_retry_at = ?"
                params.append(next_retry_at)
                
            if to_state in ["ACKNOWLEDGED", "COMPLETED"]:
                update_sql += ", sync_timestamp = ?, next_retry_at = NULL"
                params.append(now)
                
            update_sql += " WHERE event_id = ?"
            params.append(event_id)
            
            cursor.execute(update_sql, tuple(params))
            
            # Log transition
            cursor.execute(
                """
                INSERT INTO sync_state_transitions (event_id, from_state, to_state, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, from_state, to_state, reason, now)
            )
            
            if to_state in ["COMPLETED", "FAILED"]:
                # Remove from sync queue if present
                cursor.execute("DELETE FROM sync_queue WHERE event_id = ?", (event_id,))
                
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.debug(f"Event {event_id} transitioned from {from_state} to {to_state}")
                return True
            return False
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to transition state for event {event_id}: {e}")
            return False

    def recover_sending_events(self) -> int:
        """
        Recover events that were left in SENDING state (e.g. after a crash).
        Transitions them back to QUEUED.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            
            cursor.execute("BEGIN IMMEDIATE")
            
            cursor.execute("SELECT event_id FROM recognition_events WHERE sync_status = 'SENDING'")
            rows = cursor.fetchall()
            
            count = 0
            for row in rows:
                event_id = row["event_id"]
                cursor.execute(
                    "UPDATE recognition_events SET sync_status = 'QUEUED' WHERE event_id = ?",
                    (event_id,)
                )
                cursor.execute(
                    """
                    INSERT INTO sync_state_transitions (event_id, from_state, to_state, reason, created_at)
                    VALUES (?, 'SENDING', 'QUEUED', 'Process crash recovery', ?)
                    """,
                    (event_id, now)
                )
                count += 1
                
            conn.commit()
            if count > 0:
                logger.info(f"Recovered {count} events from SENDING to QUEUED state")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to recover sending events: {e}")
            return 0
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single event by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM recognition_events WHERE event_id = ?",
                (event_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to fetch event: {e}")
            return None

    def get_events_by_camera(
        self,
        camera_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch events by camera ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM recognition_events 
                WHERE camera_id = ?
                ORDER BY sequence_number DESC
                LIMIT ? OFFSET ?
                """,
                (camera_id, limit, offset)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch events by camera: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get ledger statistics."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT COUNT(*) as total FROM recognition_events WHERE device_id = ?",
                (self.device_id,)
            )
            total = cursor.fetchone()["total"] or 0
            
            cursor.execute(
                "SELECT COUNT(*) as pending FROM recognition_events WHERE device_id = ? AND sync_status IN ('QUEUED', 'RETRYING')",
                (self.device_id,)
            )
            pending = cursor.fetchone()["pending"] or 0
            
            cursor.execute(
                "SELECT COUNT(*) as synced FROM recognition_events WHERE device_id = ? AND sync_status = 'COMPLETED'",
                (self.device_id,)
            )
            synced = cursor.fetchone()["synced"] or 0
            
            cursor.execute(
                "SELECT COUNT(*) as failed FROM recognition_events WHERE device_id = ? AND sync_status = 'FAILED'",
                (self.device_id,)
            )
            failed = cursor.fetchone()["failed"] or 0
            
            cursor.execute(
                "SELECT priority, COUNT(*) as count FROM sync_queue GROUP BY priority"
            )
            priority_counts = {row["priority"]: row["count"] for row in cursor.fetchall()}
            
            return {
                "total_events": total,
                "pending_sync": pending,
                "failed_sync": failed,
                "priority_queue": priority_counts
            }
        except Exception as e:
            logger.error(f"Failed to get ledger stats: {e}")
            return {"error": str(e)}

    def prevent_starvation(self, max_wait_seconds: int = 300, boost_amount: int = 10) -> int:
        """
        Boost priority of events that have been in the queue too long to prevent starvation.
        
        Args:
            max_wait_seconds: Threshold for boosting priority
            boost_amount: Amount to increase priority
            
        Returns:
            Number of events boosted
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            threshold = (datetime.now(timezone.utc).timestamp() - max_wait_seconds)
            # created_at is ISO string. SQLite can compare strings or we just boost based on it.
            # actually we can use strftime
            cursor.execute("BEGIN IMMEDIATE")
            
            cursor.execute(
                """
                UPDATE sync_queue 
                SET priority = priority + ? 
                WHERE priority < 100 AND strftime('%s', created_at) < strftime('%s', 'now', ?)
                """,
                (boost_amount, f"-{max_wait_seconds} seconds")
            )
            boosted = cursor.rowcount
            conn.commit()
            
            if boosted > 0:
                logger.info(f"Boosted priority of {boosted} events to prevent starvation")
                
            return boosted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to prevent starvation: {e}")
            return 0

    def get_sync_metadata(self) -> List[Dict[str, Any]]:
        """
        Calculate the synchronization boundaries for all cameras on this device.
        
        Returns:
            List of camera metadata dicts:
            [
                {
                    "camera_id": "cam-1",
                    "highest_local_sequence": 100,
                    "lowest_pending_sequence": 90, # None if no pending
                    "last_completed_sequence": 89  # None if none completed
                }
            ]
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Fetch all cameras from sequence manager
            all_device_infos = self.sequence_manager.get_all_sequence_info()
            device_infos = [info for info in all_device_infos if info.device_id == self.device_id]
            
            metadata = []
            for info in device_infos:
                cam_id = info.camera_id
                
                # Get lowest pending
                cursor.execute(
                    """
                    SELECT MIN(sequence_number) as lowest_pending 
                    FROM recognition_events 
                    WHERE device_id = ? AND camera_id = ? 
                    AND sync_status IN ('QUEUED', 'SENDING', 'RETRYING')
                    """,
                    (self.device_id, cam_id)
                )
                lowest_pending = cursor.fetchone()["lowest_pending"]
                
                # Get last completed
                cursor.execute(
                    """
                    SELECT MAX(sequence_number) as last_completed
                    FROM recognition_events
                    WHERE device_id = ? AND camera_id = ?
                    AND sync_status = 'COMPLETED'
                    """,
                    (self.device_id, cam_id)
                )
                last_completed = cursor.fetchone()["last_completed"]
                
                metadata.append({
                    "camera_id": cam_id,
                    "highest_local_sequence": info.current_sequence,
                    "lowest_pending_sequence": lowest_pending,
                    "last_completed_sequence": last_completed
                })
                
            return metadata
        except Exception as e:
            logger.error(f"Failed to get sync metadata: {e}")
            return []

    def requeue_sequence_ranges(self, camera_id: str, missing_ranges: List[Tuple[int, int]]) -> int:
        """
        Requeue specific sequence ranges for retransmission.
        
        Transitions sequences within the ranges that are not already QUEUED
        into the QUEUED state, resetting their retry counters.
        
        Args:
            camera_id: Target camera ID
            missing_ranges: List of [start, end] inclusive sequence ranges
            
        Returns:
            Number of events successfully requeued
        """
        if not missing_ranges:
            return 0
            
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            
            cursor.execute("BEGIN IMMEDIATE")
            
            total_requeued = 0
            for start_seq, end_seq in missing_ranges:
                # Find events in range that are not QUEUED
                cursor.execute(
                    """
                    SELECT event_id, sync_status FROM recognition_events
                    WHERE device_id = ? AND camera_id = ? 
                    AND sequence_number >= ? AND sequence_number <= ?
                    AND sync_status != 'QUEUED'
                    """,
                    (self.device_id, camera_id, start_seq, end_seq)
                )
                events = cursor.fetchall()
                
                for row in events:
                    event_id = row["event_id"]
                    old_status = row["sync_status"]
                    
                    cursor.execute(
                        """
                        UPDATE recognition_events
                        SET sync_status = 'QUEUED', retry_count = 0, next_retry_at = NULL
                        WHERE event_id = ?
                        """,
                        (event_id,)
                    )
                    
                    # Update sync queue priority to high (1)
                    cursor.execute(
                        """
                        INSERT INTO sync_queue (event_id, priority, created_at)
                        VALUES (?, 1, ?)
                        ON CONFLICT(event_id) DO UPDATE SET priority = 1
                        """,
                        (event_id, now)
                    )
                    
                    # Audit transition
                    cursor.execute(
                        """
                        INSERT INTO sync_state_transitions (event_id, from_state, to_state, reason, created_at)
                        VALUES (?, ?, 'QUEUED', 'Reconciliation requeue', ?)
                        """,
                        (event_id, old_status, now)
                    )
                    
                    total_requeued += 1
            
            conn.commit()
            if total_requeued > 0:
                logger.info(f"Requeued {total_requeued} missing events for camera {camera_id}")
            return total_requeued
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to requeue sequence ranges: {e}")
            return 0

    def cleanup_old_synced_events(self, days: int = 30) -> int:
        """
        Remove synced events older than N days (archive offline).

        Args:
            days: Age threshold in days

        Returns:
            Number of rows deleted
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cutoff = datetime.now(timezone.utc)
            cutoff = cutoff.replace(
                day=cutoff.day - days
            )
            
            cursor.execute(
                """
                DELETE FROM recognition_events 
                WHERE device_id = ? 
                AND sync_status = 'COMPLETED'
                AND created_at < ?
                """,
                (self.device_id, cutoff.isoformat())
            )
            conn.commit()
            
            deleted = cursor.rowcount
            logger.info(f"Cleaned {deleted} old synced events")
            return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup old events: {e}")
            return 0

    def get_sequence_info(self, camera_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get sequence tracking information.
        
        Args:
            camera_id: If provided, get info for specific camera.
                      If None, get info for all cameras on this device.
        
        Returns:
            Dictionary with sequence information:
            {
                "device_id": "edge-01",
                "cameras": [
                    {
                        "camera_id": "front-door",
                        "current_sequence": 42,
                        "event_count": 42,
                        "last_updated": "2026-01-15T14:30:00+00:00"
                    }
                ]
            }
        """
        if camera_id:
            seq_info = self.sequence_manager.get_sequence_info(self.device_id, camera_id)
            return {
                "device_id": self.device_id,
                "camera_id": camera_id,
                "current_sequence": seq_info.current_sequence if seq_info else 0,
                "event_count": seq_info.event_count if seq_info else 0,
                "last_updated": seq_info.last_updated.isoformat() if seq_info else None,
            }
        else:
            all_infos = self.sequence_manager.get_all_sequence_info()
            device_infos = [
                info for info in all_infos
                if info.device_id == self.device_id
            ]
            return {
                "device_id": self.device_id,
                "cameras": [
                    {
                        "camera_id": info.camera_id,
                        "current_sequence": info.current_sequence,
                        "event_count": info.event_count,
                        "last_updated": info.last_updated.isoformat(),
                    }
                    for info in device_infos
                ]
            }

    def detect_sequence_anomalies(self, camera_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Detect sequence anomalies (gaps, duplicates, out-of-order events).
        
        Args:
            camera_id: If provided, check specific camera.
                      If None, check all cameras on this device.
        
        Returns:
            Dictionary with anomaly information:
            {
                "device_id": "edge-01",
                "anomalies": [
                    {
                        "type": "gap",
                        "camera_id": "front-door",
                        "start_sequence": 10,
                        "end_sequence": 19,
                        "count": 10
                    }
                ],
                "summary": {
                    "total_anomalies": 1,
                    "duplicates": 0,
                    "gaps": 1,
                    "out_of_order": 0
                }
            }
        """
        anomalies = self.sequence_manager.get_anomalies(
            device_id=self.device_id,
            camera_id=camera_id,
            limit=1000
        )
        
        gaps = []
        if camera_id:
            gaps = self.sequence_manager.detect_gaps(self.device_id, camera_id)
        else:
            # Get all cameras on this device
            all_infos = self.sequence_manager.get_all_sequence_info()
            device_cameras = {
                info.camera_id for info in all_infos
                if info.device_id == self.device_id
            }
            for cam_id in device_cameras:
                gaps.extend(self.sequence_manager.detect_gaps(self.device_id, cam_id))
        
        # Build anomaly response
        anomaly_list = []
        
        # Add gap information
        for gap in gaps:
            anomaly_list.append({
                "type": "gap",
                "camera_id": gap.start if isinstance(gap, dict) else "unknown",
                "start_sequence": gap.start,
                "end_sequence": gap.end,
                "count": gap.count
            })
        
        # Add detected anomalies
        for anomaly in anomalies:
            anomaly_list.append({
                "type": anomaly.anomaly_type,
                "camera_id": anomaly.camera_id,
                "expected_sequence": anomaly.expected_sequence,
                "received_sequence": anomaly.received_sequence,
                "timestamp": anomaly.timestamp.isoformat(),
                "details": anomaly.details
            })
        
        # Count by type
        summary = {
            "total_anomalies": len(anomaly_list),
            "duplicates": len([a for a in anomaly_list if a["type"] == "duplicate"]),
            "gaps": len([a for a in anomaly_list if a["type"] == "gap"]),
            "out_of_order": len([a for a in anomaly_list if a["type"] == "out_of_order"])
        }
        
        return {
            "device_id": self.device_id,
            "camera_id": camera_id,
            "anomalies": anomaly_list,
            "summary": summary
        }



    def close(self) -> None:
        """Close database connection."""
        try:
            if hasattr(self._local, "conn") and self._local.conn:
                self._local.conn.close()
                self._local.conn = None
        except Exception as e:
            logger.warning(f"Error closing database: {e}")


class EventLedgerMigrator:
    """Migrate existing CSV files to EventLedger."""

    @staticmethod
    def migrate_csv_files(
        csv_dir: str,
        ledger: EventLedger,
        pattern: str = "detections-*.csv",
    ) -> Dict[str, int]:
        """
        Migrate CSV files to event ledger.

        Args:
            csv_dir: Directory containing CSV files
            ledger: EventLedger instance
            pattern: Glob pattern for CSV files

        Returns:
            Dictionary with migration status
        """
        import csv
        from datetime import datetime
        
        csv_path = Path(csv_dir)
        csv_files = list(csv_path.glob(pattern))
        
        results = {
            "total_files": len(csv_files),
            "total_events": 0,
            "skipped_events": 0,
            "errors": 0,
        }
        
        for csv_file in csv_files:
            logger.info(f"Migrating {csv_file.name}")
            try:
                with open(csv_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    
                    for row_num, row in enumerate(reader, start=2):
                        try:
                            # Parse row
                            timestamp_str = row.get("timestamp", "")
                            camera_id = row.get("camera_id", "unknown")
                            identity = row.get("identity", "Unknown")
                            confidence_str = row.get("confidence", "0.0")
                            bbox_str = row.get("bbox", "[0,0,0,0]")
                            
                            # Convert confidence
                            try:
                                confidence = float(confidence_str)
                            except (ValueError, TypeError):
                                confidence = 0.0
                            
                            # Create event
                            dedup_key = f"{camera_id}:{identity}"
                            
                            ledger.add_event(
                                camera_id=camera_id,
                                identity=identity,
                                confidence=confidence,
                                dedup_key=dedup_key,
                                event_payload={
                                    "bbox": bbox_str,
                                    "source": "csv_migration",
                                },
                            )
                            results["total_events"] += 1
                            
                        except Exception as e:
                            logger.warning(f"Failed to migrate row {row_num}: {e}")
                            results["errors"] += 1
                
                # Record migration
                conn = ledger._get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO migration_status (source_file, event_count, migrated_at, status)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            csv_file.name,
                            results["total_events"],
                            datetime.now(timezone.utc).isoformat(),
                            "success",
                        )
                    )
                    conn.commit()
                except Exception as e:
                    logger.error(f"Failed to record migration: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to migrate {csv_file.name}: {e}")
                results["errors"] += 1
        
        logger.info(f"Migration complete: {results}")
        return results

    @staticmethod
    def export_to_csv(
        ledger: EventLedger,
        output_path: str,
        sync_status: Optional[str] = None,
    ) -> int:
        """
        Export events from ledger to CSV.

        Args:
            ledger: EventLedger instance
            output_path: Output CSV file path
            sync_status: Filter by status (None = all)

        Returns:
            Number of events exported
        """
        import csv
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        conn = ledger._get_connection()
        try:
            cursor = conn.cursor()
            
            if sync_status:
                cursor.execute(
                    """
                    SELECT * FROM recognition_events 
                    WHERE device_id = ? AND sync_status = ?
                    ORDER BY sequence_number ASC
                    """,
                    (ledger.device_id, sync_status)
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM recognition_events 
                    WHERE device_id = ?
                    ORDER BY sequence_number ASC
                    """,
                    (ledger.device_id,)
                )
            
            rows = cursor.fetchall()
            
            if not rows:
                logger.info("No events to export")
                return 0
            
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "event_id",
                        "device_id",
                        "camera_id",
                        "sequence_number",
                        "capture_timestamp",
                        "identity",
                        "confidence",
                        "model_version",
                        "age",
                        "gender",
                        "created_at",
                        "sync_status",
                    ],
                )
                writer.writeheader()
                
                for row in rows:
                    writer.writerow({
                        "event_id": row["event_id"],
                        "device_id": row["device_id"],
                        "camera_id": row["camera_id"],
                        "sequence_number": row["sequence_number"],
                        "capture_timestamp": row["capture_timestamp"],
                        "identity": row["identity"],
                        "confidence": row["confidence"],
                        "model_version": row["model_version"],
                        "age": row["age"],
                        "gender": row["gender"],
                        "created_at": row["created_at"],
                        "sync_status": row["sync_status"],
                    })
            
            logger.info(f"Exported {len(rows)} events to {output_file}")
            return len(rows)
            
        except Exception as e:
            logger.error(f"Failed to export events: {e}")
            return 0
