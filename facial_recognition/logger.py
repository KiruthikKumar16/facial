import csv
import os
import threading
import queue
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional, Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class DetectionLogger:
    """Thread-safe daily CSV logger with background database sync and duplicate suppression.

    - Writes daily files to CSV (e.g., `detections-2026-08-11.csv`)
    - Writes to PostgreSQL via a background thread to prevent FPS drops
    - Suppresses duplicate records (same camera_id, identity, bbox) within a short window
    """

    def __init__(
        self,
        log_path: str,
        dedup_window_seconds: int = 60,
        db_url: Optional[str] = None,
        profile_lookup: Optional[Any] = None,
    ) -> None:
        self.base_path = Path(log_path)
        self.dir = self.base_path.parent if self.base_path.parent != Path('') else Path('.')
        self.base_name = self.base_path.stem or 'detections'
        os.makedirs(self.dir, exist_ok=True)

        self.lock = threading.Lock()
        self.current_date: str | None = None
        self.current_file = None
        self.current_writer = None

        # dedup store: maps key -> last_timestamp_seconds
        self._dedup: dict[Tuple[str, str, Tuple[int, int, int, int]], float] = {}
        self._dedup_window = float(dedup_window_seconds)

        self.profile_lookup = profile_lookup
        
        # Setup background worker for database I/O to avoid dropping camera FPS
        self.log_queue = queue.Queue()
        self._stop_event = threading.Event()
        self.db_url = db_url
        self._ensured_cameras = set()
        self._ensured_profiles = set()
        
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def _worker_loop(self):
        """Background thread to handle synchronous database writes and HTTP requests."""
        db_session = None
        if self.db_url:
            try:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                engine = create_engine(self.db_url, echo=False)
                SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                db_session = SessionLocal()
                logger.info("✓ Database connection established for real-time logging (Worker)")
            except Exception as e:
                logger.warning(f"⚠ Could not connect to database: {e}. Falling back to CSV only.")
        
        import urllib.request
        import os
        api_url = os.environ.get("API_URL", "http://localhost:8000").rstrip('/')
        
        while not self._stop_event.is_set():
            try:
                item = self.log_queue.get(timeout=1.0)
            except queue.Empty:
                continue
                
            camera_id, identity, confidence, bbox, now = item
            
            if db_session:
                try:
                    self._write_to_db(db_session, camera_id, identity, confidence, bbox, now)
                    
                    # Notify backend to trigger WebSocket updates
                    req = urllib.request.Request(f"{api_url}/api/internal/notify_update", method="POST")
                    with urllib.request.urlopen(req, timeout=1.5) as f:
                        pass
                except Exception as e:
                    logger.warning(f"Background DB/API task error: {e}")
                    
            self.log_queue.task_done()
            
        if db_session:
            db_session.close()

    def _open_for_date(self, date_str: str):
        if self.current_date == date_str and self.current_file is not None:
            return

        # close previous
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
        # remove entries older than twice the dedup window to keep memory bounded
        expiry = now_ts - (self._dedup_window * 2.0)
        keys_to_delete = [k for k, t in self._dedup.items() if t < expiry]
        for k in keys_to_delete:
            del self._dedup[k]

    def log_detection(self, camera_id: str, bbox: list[int], identity: str, confidence: float) -> None:
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        date_str = now.strftime('%Y-%m-%d')

        left, top, right, bottom = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
        
        # Track by camera and identity to suppress spam when the person moves slightly
        key = (camera_id, identity)

        with self.lock:
            # purge old dedup entries occasionally
            self._purge_dedup(now_ts)

            last = self._dedup.get(key)
            if last is not None and (now_ts - last) < self._dedup_window:
                # duplicate within window; skip logging
                print(f"[SUPPRESS] {now.isoformat()} {camera_id} [{left}, {top}, {right}, {bottom}] -> {identity} ({confidence:.4f})")
                return

            # mark as seen
            self._dedup[key] = now_ts

            # ensure file opened for the day
            self._open_for_date(date_str)

            row = {
                'timestamp': now.isoformat(timespec='seconds').replace('+00:00', 'Z'),
                'camera_id': camera_id,
                'bbox': f'[{left}, {top}, {right}, {bottom}]',
                'identity': identity,
                'confidence': f'{confidence:.4f}',
            }
            
            # Write to CSV synchronously
            try:
                self.current_writer.writerow(row)
                self.current_file.flush()
            except Exception as e:
                logger.warning(f"Failed to write CSV: {e}")

            # Send to background worker for Database I/O
            self.log_queue.put((camera_id, identity, confidence, bbox, now))

        print(f"[{row['timestamp']}] {camera_id} {row['bbox']} -> {identity} ({confidence:.4f})")

    def _write_to_db(self, db_session, camera_id: str, identity: str, confidence: float, bbox: list[int], timestamp: datetime) -> None:
        """Write detection to PostgreSQL database."""
        try:
            # Import here to avoid circular dependency
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            backend_dir = os.path.join(parent_dir, "backend")
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)
                
            from backend.models import Detection, DetectionStatus as DetectionStatusEnum, Camera
            
            # Ensure camera exists to prevent ForeignKeyViolation
            if camera_id not in self._ensured_cameras:
                existing_cam = db_session.query(Camera).filter_by(id=camera_id).first()
                if not existing_cam:
                    new_cam = Camera(id=camera_id, name=camera_id, status="online")
                    db_session.add(new_cam)
                    db_session.commit()
                self._ensured_cameras.add(camera_id)
            
            # Determine profile and status
            profile_id = None
            status = DetectionStatusEnum.unknown
            
            if self.profile_lookup and identity != "Unknown":
                profile_id = self.profile_lookup(identity)
                if profile_id:
                    status = DetectionStatusEnum.recognized
                    
                    # Ensure profile exists to prevent ForeignKeyViolation
                    if profile_id not in self._ensured_profiles:
                        from backend.models import Profile, ProfileRole
                        existing_profile = db_session.query(Profile).filter_by(id=profile_id).first()
                        if not existing_profile:
                            new_profile = Profile(id=profile_id, name=identity, role=ProfileRole.employee)
                            db_session.add(new_profile)
                            db_session.commit()
                        self._ensured_profiles.add(profile_id)
            elif identity == "Unknown":
                status = DetectionStatusEnum.unknown
            
            # Create detection record
            detection = Detection(
                id=str(uuid4()),
                camera_id=camera_id,
                profile_id=profile_id,
                timestamp=timestamp,
                status=status,
                confidence=confidence,
                bbox=f"[{int(bbox[0])}, {int(bbox[1])}, {int(bbox[2])}, {int(bbox[3])}]",
                liveness_score=0.0,
                age=None,
                gender="unknown",
                wearing_mask=False,
                wearing_glasses=False,
            )
            
            db_session.add(detection)
            db_session.commit()
            
        except Exception as e:
            logger.warning(f"Failed to write detection to database: {e}")
            try:
                db_session.rollback()
            except Exception:
                pass

    def close(self) -> None:
        self._stop_event.set()
        
        with self.lock:
            try:
                if self.current_file is not None:
                    self.current_file.close()
            except Exception:
                pass

    def __del__(self) -> None:
        """Cleanup on garbage collection."""
        self.close()
