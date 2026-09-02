"""Thread-safe detection logging with offline-first SQLite ledger and CSV fallback.

Architecture:
- Primary: SQLite EventLedger (transactional, recoverable, indexed)
- Secondary: CSV export (backward compatibility, human readable)
- Sync: Background thread for async cloud transmission with retry logic

Event lifecycle:
1. Check deduplication window
2. Log event to SQLite (transactional, synchronous)
3. Queue for sync (added to sync_queue table)
4. Background worker: drain queue, POST to /api/detections
5. Mark synced/failed in database
6. Optional: periodic CSV export for offline review
"""

import csv
import os
import threading
import queue
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

try:
    from .event_ledger import EventLedger, EventLedgerMigrator
    from .network import NetworkMonitor, NetworkState
except ImportError:
    from event_ledger import EventLedger, EventLedgerMigrator
    from network import NetworkMonitor, NetworkState

logger = logging.getLogger(__name__)

class PriorityRuleEngine:
    @staticmethod
    def get_priority(identity: str, confidence: float, role: str = None) -> Tuple[int, str]:
        """
        Determine event priority based on configurable rules.
        Returns: (priority_integer, priority_string)
        100 = CRITICAL, 75 = HIGH, 50 = NORMAL, 25 = LOW
        """
        # Example hardcoded rules based on requirements
        if role == "blacklist":
            return 100, "critical"
        if confidence >= 0.90:
            return 75, "high"
        if identity and identity not in ["Unknown", ""]:
            return 50, "normal"
        return 25, "low"


class DetectionLogger:
    """Thread-safe detection logger with SQLite ledger + CSV backup.

    Combines:
    - SQLite-backed event ledger (primary, transactional)
    - CSV export (backward compatibility)
    - Background sync worker with retry logic
    - Deduplication within configurable window
    """

    def __init__(
        self,
        log_path: str,
        dedup_window_seconds: int = 60,
        db_url: Optional[str] = None,
        profile_lookup: Optional[object] = None,
        ledger_db_path: str = "facial_recognition.db",
        enable_wal: bool = True,
        export_csv: bool = True,
    ) -> None:
        """
        Initialize detection logger.

        Args:
            log_path: Directory for CSV files (backward compat)
            dedup_window_seconds: Deduplication window in seconds
            db_url: PostgreSQL URL (for background sync)
            profile_lookup: Profile lookup callable (unused, for compatibility)
            ledger_db_path: SQLite database path
            enable_wal: Enable WAL mode for SQLite
            export_csv: Whether to export to CSV after each event
        """
        self.base_path = Path(log_path)
        self.dir = self.base_path.parent if self.base_path.parent != Path('') else Path('.')
        self.base_name = self.base_path.stem or 'detections'
        os.makedirs(self.dir, exist_ok=True)

        self.lock = threading.Lock()
        self.current_date: Optional[str] = None
        self.current_file = None
        self.current_writer = None
        self.export_csv = export_csv

        # Deduplication: maps (camera_id, identity) -> timestamp
        self._dedup: dict[Tuple[str, str], float] = {}
        self._dedup_window = float(dedup_window_seconds)

        self.profile_lookup = profile_lookup

        # Initialize SQLite event ledger
        self.ledger = EventLedger(
            db_path=ledger_db_path,
            enable_wal=enable_wal,
        )
        
        # Background sync worker
        self.log_queue = queue.Queue()
        self._stop_event = threading.Event()
        self.db_url = db_url
        self.network_monitor = NetworkMonitor()
        
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

        logger.info(f"DetectionLogger initialized with ledger at {ledger_db_path}")

    def _open_for_date(self, date_str: str) -> None:
        """Open CSV file for the given date (backward compatibility)."""
        if self.current_date == date_str and self.current_file is not None:
            return

        # Close previous
        try:
            if self.current_file is not None:
                self.current_file.close()
        except Exception:
            pass

        filename = f"{self.base_name}-{date_str}.csv"
        path = self.dir / filename
        is_new = not path.exists()
        self.current_file = open(path, 'a', newline='', encoding='utf-8')
        self.current_writer = csv.DictWriter(
            self.current_file,
            fieldnames=['timestamp', 'camera_id', 'bbox', 'identity', 'confidence'],
        )
        if is_new or self.current_file.tell() == 0:
            self.current_writer.writeheader()
            self.current_file.flush()
        self.current_date = date_str

    def _purge_dedup(self, now_ts: float) -> None:
        """Remove dedup entries older than 2x dedup window."""
        expiry = now_ts - (self._dedup_window * 2.0)
        keys_to_delete = [k for k, t in self._dedup.items() if t < expiry]
        for k in keys_to_delete:
            del self._dedup[k]

    def log_detection(
        self,
        camera_id: str,
        bbox: list,
        identity: str,
        confidence: float,
        age: Optional[int] = None,
        gender: Optional[str] = None,
        quality_score: Optional[float] = None,
        embedding: Optional[Any] = None,
        config_version: Optional[int] = 1,
        version_bundle: Optional[Any] = None,
        provenance: Optional[Any] = None,
    ) -> Optional[str]:
        """
        Log a detection event (main entry point).

        Event is persisted to SQLite first (transactionally).
        Then optionally exported to CSV.
        Finally queued for async cloud sync.

        Args:
            camera_id: Camera identifier
            bbox: Bounding box [x1, y1, x2, y2]
            identity: Person name or "Unknown"/"Person N"
            confidence: Recognition confidence
            age: Estimated age
            gender: Estimated gender
            quality_score: Estimated face quality score
            config_version: Active camera configuration version
            version_bundle: ModelConfigVersionBundle snapshot
            provenance: RecognitionProvenance or lineage dictionary

        Returns:
            event_id: Unique event identifier, or None if deduplicated
        """
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        date_str = now.strftime('%Y-%m-%d')

        left, top, right, bottom = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        dedup_key = (camera_id, identity)
        
        # We need the profile role to assign priority correctly, but for now we simulate it or pass None
        priority_int, priority_str = PriorityRuleEngine.get_priority(identity, confidence)

        # Prepare payload dictionary
        prov_dict = provenance.to_dict() if hasattr(provenance, 'to_dict') else provenance
        bundle_dict = version_bundle.to_dict() if hasattr(version_bundle, 'to_dict') else version_bundle

        event_payload = {
            "bbox": [left, top, right, bottom],
            "box_formatted": f"[{left}, {top}, {right}, {bottom}]",
            "quality_score": quality_score,
            "provenance": prov_dict,
            "version_bundle": bundle_dict,
            "embedding": embedding.tolist() if hasattr(embedding, "tolist") else embedding,
        }

        with self.lock:
            # Check deduplication
            self._purge_dedup(now_ts)
            last = self._dedup.get(dedup_key)
            
            if last is not None and (now_ts - last) < self._dedup_window:
                logger.debug(
                    f"[DEDUPLICATE] {camera_id} {identity} "
                    f"within {now_ts - last:.1f}s of last event"
                )
                return None

            # Mark as seen
            self._dedup[dedup_key] = now_ts

            # Step 1: Persist to SQLite ledger (PRIMARY)
            try:
                event_id = self.ledger.add_event(
                    camera_id=camera_id,
                    identity=identity,
                    confidence=float(confidence),
                    age=age,
                    gender=gender,
                    event_payload=event_payload,
                    dedup_key=f"{camera_id}:{identity}",
                    capture_timestamp=now,
                    priority=priority_int,
                    config_version=config_version or 1,
                )
            except Exception as e:
                logger.error(f"Failed to persist to ledger: {e}")
                return None

            # Step 2: Export to CSV for backward compatibility (OPTIONAL)
            if self.export_csv:
                try:
                    self._open_for_date(date_str)
                    row = {
                        'timestamp': now.isoformat(timespec='seconds').replace('+00:00', 'Z'),
                        'camera_id': camera_id,
                        'bbox': f'[{left}, {top}, {right}, {bottom}]',
                        'identity': identity,
                        'confidence': f'{confidence:.4f}',
                    }
                    self.current_writer.writerow(row)
                    self.current_file.flush()
                except Exception as e:
                    logger.warning(f"Failed to write CSV: {e}")

            # Step 3: Queue for sync (background thread will send to cloud)
            self.log_queue.put((event_id, camera_id, identity, confidence, bbox, now, age, gender))

            logger.info(
                f"[{now.isoformat(timespec='seconds')}] "
                f"{camera_id} [{left}, {top}, {right}, {bottom}] "
                f"-> {identity} ({confidence:.4f}) [event_id={event_id}]"
            )
            
            return event_id

    def _run_reconciliation(self, api_url: str, api_key: str) -> None:
        """Run periodic reconciliation to fetch missing sequences."""
        import urllib.request
        import json
        
        try:
            metadata = self.ledger.get_sync_metadata()
            if not metadata:
                return
                
            payload = {
                "device_id": self.ledger.device_id,
                "cameras": metadata
            }
            
            req = urllib.request.Request(
                f"{api_url}/api/detections/reconcile",
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'X-API-Key': api_key
                },
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10.0) as f:
                response_data = json.loads(f.read().decode('utf-8'))
                
            for cam_res in response_data.get('reconciled_cameras', []):
                cam_id = cam_res.get('camera_id')
                missing_ranges = cam_res.get('missing_ranges', [])
                if missing_ranges:
                    self.ledger.requeue_sequence_ranges(cam_id, missing_ranges)
                    
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")

    def _worker_loop(self) -> None:
        """Background thread for cloud sync with retry logic."""
        import urllib.request
        from urllib.error import HTTPError, URLError
        import json
        import time
        import random
        from datetime import datetime, timedelta, timezone

        api_url = os.environ.get("API_URL", "http://localhost:1223").rstrip('/')
        api_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
        
        # Recover any events stranded in SENDING state during a previous process crash
        self.ledger.recover_sending_events()

        max_retries = 5
        base_backoff = 2.0
        max_backoff = 300.0
        
        last_reconciliation = 0.0
        reconciliation_interval = 60.0
        last_starvation_check = 0.0
        starvation_interval = 120.0

        while not self._stop_event.is_set():
            now_ts = time.time()
            if now_ts - last_reconciliation >= reconciliation_interval:
                self._run_reconciliation(api_url, api_key)
                last_reconciliation = time.time()
                
            if now_ts - last_starvation_check >= starvation_interval:
                self.ledger.prevent_starvation(max_wait_seconds=300, boost_amount=25)
                last_starvation_check = time.time()
                
            network_state = self.network_monitor.get_state()
            
            # Determine loop parameters based on network state
            if network_state == NetworkState.GOOD:
                batch_limit = 50
                sleep_delay = 1.0
            elif network_state == NetworkState.DEGRADED:
                batch_limit = 20
                sleep_delay = 5.0
            else: # OFFLINE
                batch_limit = 10
                sleep_delay = 10.0
                
            # Get events ready for sync (QUEUED or RETRYING where next_retry_at is due)
            pending = self.ledger.get_pending_events(limit=batch_limit)
            
            if not pending:
                time.sleep(sleep_delay)
                continue

            critical_events = []
            batched_events = []

            for event in pending:
                event_id = event['event_id']
                camera_id = event['camera_id']
                identity = event['identity']
                confidence = float(event['confidence'])
                retry_count = event.get('retry_count', 0)
                queue_priority = event.get('queue_priority', 10)
                
                is_critical = queue_priority >= 75
                
                # In OFFLINE state, skip non-critical events
                if network_state == NetworkState.OFFLINE and not is_critical:
                    continue
                
                # Transition to SENDING before attempting network operation
                if not self.ledger.transition_state(event_id, "SENDING", reason="Attempting sync"):
                    continue
                
                # Parse bbox from event payload
                try:
                    import json as json_lib
                    payload = json_lib.loads(event['event_payload'] or '{}')
                    bbox = payload.get('bbox', [0, 0, 0, 0])
                except Exception:
                    bbox = [0, 0, 0, 0]

                # Map priority back to string enum
                priority_str = "normal"
                if queue_priority >= 100: priority_str = "critical"
                elif queue_priority >= 75: priority_str = "high"
                elif queue_priority <= 25: priority_str = "low"

                api_payload = {
                    "camera_id": camera_id,
                    "identity": identity,
                    "confidence": confidence,
                    "bbox": [int(x) for x in bbox],
                    "timestamp": event['capture_timestamp'],
                    "event_id": event_id,  # Idempotency key
                    "device_id": event.get("device_id"),
                    "sequence_number": event.get("sequence_number"),
                    "priority": priority_str,
                    "config_version": event.get("config_version", 1),
                }
                if payload.get("embedding") is not None:
                    api_payload["embedding"] = payload["embedding"]
                
                if event.get('age') is not None:
                    api_payload["age"] = int(event['age'])
                if event.get('gender'):
                    api_payload["gender"] = str(event['gender'])

                # Provenance and Version Tracking
                if payload.get("provenance"):
                    api_payload["provenance"] = payload["provenance"]
                if payload.get("version_bundle"):
                    v_b = payload["version_bundle"]
                    api_payload["detection_model_version"] = v_b.get("detection_model_version")
                    api_payload["embedding_model_version"] = v_b.get("embedding_model_version")
                    api_payload["gallery_version"] = v_b.get("gallery_version")
                    api_payload["threshold_version"] = v_b.get("threshold_version")
                    api_payload["camera_config_version"] = v_b.get("camera_config_version")
                    api_payload["algorithm_version"] = v_b.get("algorithm_version")
                    api_payload["version_bundle_hash"] = v_b.get("bundle_hash")

                if is_critical:
                    critical_events.append((event, api_payload))
                else:
                    batched_events.append((event, api_payload))

            # Helper to handle network response for events
            def handle_result(event, api_payload, error_code=None, error_reason=None, is_fatal=False):
                event_id = event['event_id']
                retry_count = event.get('retry_count', 0)
                queue_priority = event.get('queue_priority', 10)
                is_critical = queue_priority >= 75
                
                if not error_reason:
                    # Success
                    self.ledger.transition_state(event_id, "ACKNOWLEDGED", reason="Server returned 2xx")
                    self.ledger.transition_state(event_id, "COMPLETED", reason="Sync finished successfully")
                    logger.debug(f"Event {event_id} synced to cloud and COMPLETED")
                else:
                    # Handle Failure
                    if is_fatal or (not is_critical and retry_count >= max_retries):
                        self.ledger.transition_state(
                            event_id, 
                            "FAILED", 
                            reason=f"Fatal error or max retries exceeded: {error_reason}"
                        )
                        logger.warning(f"Event {event_id} marked as FAILED: {error_reason}")
                    else:
                        backoff = min(max_backoff, base_backoff * (2 ** retry_count))
                        jitter = random.uniform(0, backoff * 0.1)
                        wait_time = backoff + jitter
                        next_retry = (datetime.now(timezone.utc) + timedelta(seconds=wait_time)).isoformat()
                        
                        self.ledger.transition_state(
                            event_id, 
                            "RETRYING", 
                            reason=error_reason, 
                            increment_retry=True,
                            next_retry_at=next_retry
                        )
                        logger.info(f"Event {event_id} RETRYING in {wait_time:.1f}s: {error_reason}")

            # Send critical events immediately (one by one for maximal reliability)
            for event, payload in critical_events:
                start_time = time.time()
                req_bytes = len(json.dumps(payload).encode('utf-8'))
                try:
                    req = urllib.request.Request(
                        f"{api_url}/api/detections",
                        data=json.dumps(payload).encode('utf-8'),
                        headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=5.0) as f:
                        pass
                    latency = (time.time() - start_time) * 1000
                    self.network_monitor.record_request(True, latency, bytes_sent=req_bytes, events_sent=1)
                    handle_result(event, payload)
                except HTTPError as e:
                    fatal = 400 <= e.code < 500 and e.code != 429
                    latency = (time.time() - start_time) * 1000
                    self.network_monitor.record_request(False, latency)
                    handle_result(event, payload, error_code=e.code, error_reason=f"HTTP {e.code}: {e.reason}", is_fatal=fatal)
                except Exception as e:
                    latency = (time.time() - start_time) * 1000
                    self.network_monitor.record_request(False, latency)
                    handle_result(event, payload, error_reason=str(e), is_fatal=False)

            # Send batched events
            if batched_events:
                start_time = time.time()
                batch_payload = {"detections": [p for _, p in batched_events]}
                req_bytes = len(json.dumps(batch_payload).encode('utf-8'))
                try:
                    req = urllib.request.Request(
                        f"{api_url}/api/detections/batch",
                        data=json.dumps(batch_payload).encode('utf-8'),
                        headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=10.0) as f:
                        pass
                    latency = (time.time() - start_time) * 1000
                    self.network_monitor.record_request(True, latency, bytes_sent=req_bytes, events_sent=len(batched_events))
                    for event, payload in batched_events:
                        handle_result(event, payload)
                except HTTPError as e:
                    fatal = 400 <= e.code < 500 and e.code != 429
                    latency = (time.time() - start_time) * 1000
                    self.network_monitor.record_request(False, latency)
                    for event, payload in batched_events:
                        handle_result(event, payload, error_code=e.code, error_reason=f"HTTP {e.code}: {e.reason}", is_fatal=fatal)
                except Exception as e:
                    latency = (time.time() - start_time) * 1000
                    self.network_monitor.record_request(False, latency)
                    for event, payload in batched_events:
                        handle_result(event, payload, error_reason=str(e), is_fatal=False)

            # Delay to yield loop and respect degraded states
            time.sleep(sleep_delay if not critical_events else 0.1)

            # Small delay to yield loop
            time.sleep(0.1)

    def get_stats(self) -> dict:
        """Get statistics from ledger."""
        stats = self.ledger.get_stats()
        stats["network_metrics"] = self.network_monitor.get_metrics()
        return stats

    def export_to_csv(self, output_path: str, sync_status: Optional[str] = None) -> int:
        """Export events to CSV file."""
        return EventLedgerMigrator.export_to_csv(
            self.ledger,
            output_path,
            sync_status=sync_status
        )

    def close(self) -> None:
        """Shutdown logger gracefully."""
        self._stop_event.set()
        if hasattr(self, 'worker') and self.worker.is_alive() and threading.current_thread() != self.worker:
            self.worker.join(timeout=1.0)
        
        with self.lock:
            try:
                if self.current_file is not None:
                    self.current_file.close()
            except Exception:
                pass
        
        self.ledger.close()

    def __del__(self) -> None:
        """Cleanup on garbage collection."""
        self.close()
