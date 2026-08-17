import csv
import os
import threading
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional, Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class DetectionLogger:
    """Thread-safe daily CSV logger with database sync and duplicate suppression.

    - Writes daily files to CSV (e.g., `detections-2026-08-11.csv`)
    - Optionally writes to PostgreSQL for real-time dashboard updates
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

        # Database connection (optional)
        self.db_session = None
        self.profile_lookup = profile_lookup  # Function to lookup profile by identity
        
        if db_url:
            try:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                
                engine = create_engine(db_url, echo=False)
                SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                self.db_session = SessionLocal()
                logger.info("✓ Database connection established for real-time logging")
            except Exception as e:
                logger.warning(f"⚠ Could not connect to database: {e}. Falling back to CSV only.")
                self.db_session = None

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
        key = (camera_id, identity, (left, top, right, bottom))

        with self.lock:
            # purge old dedup entries occasionally
            self._purge_dedup(now_ts)

            last = self._dedup.get(key)
            if last is not None and (now_ts - last) < self._dedup_window:
                # duplicate within window; skip logging
                print(f"[SUPPRESS] {now.isoformat()} {camera_id} {key[2]} -> {identity} ({confidence:.4f})")
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
            
            # Write to CSV
            try:
                self.current_writer.writerow(row)
                self.current_file.flush()
            except Exception as e:
                logger.warning(f"Failed to write CSV: {e}")

            # Write to Database (if connected)
            if self.db_session:
                self._write_to_db(camera_id, identity, confidence, bbox, now)
                
                # Notify backend to trigger WebSocket updates
                try:
                    import urllib.request
                    import os
                    api_url = os.environ.get("API_URL", "http://localhost:8000")
                    req = urllib.request.Request(
                        f"{api_url.rstrip('/')}/api/internal/notify_update", 
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=0.5) as f:
                        pass
                except Exception:
                    pass

        print(f"[{row['timestamp']}] {camera_id} {row['bbox']} -> {identity} ({confidence:.4f})")

    def _write_to_db(self, camera_id: str, identity: str, confidence: float, bbox: list[int], timestamp: datetime) -> None:
        """Write detection to PostgreSQL database."""
        try:
            # Import here to avoid circular dependency
            from backend.models import Detection, DetectionStatus as DetectionStatusEnum
            
            # Determine profile and status
            profile_id = None
            status = DetectionStatusEnum.unknown
            
            if self.profile_lookup and identity != "Unknown":
                profile_id = self.profile_lookup(identity)
                if profile_id:
                    status = DetectionStatusEnum.recognized
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
                liveness_score=0.0,  # Not available yet
                age=None,
                gender="unknown",
                wearing_mask=False,
                wearing_glasses=False,
            )
            
            self.db_session.add(detection)
            self.db_session.commit()
            
        except Exception as e:
            logger.warning(f"Failed to write to database: {e}")
            try:
                self.db_session.rollback()
            except Exception:
                pass

    def close(self) -> None:
        with self.lock:
            try:
                if self.current_file is not None:
                    self.current_file.close()
            except Exception:
                pass
            
            # Close database session
            if self.db_session:
                try:
                    self.db_session.close()
                    logger.info("Database session closed")
                except Exception as e:
                    logger.warning(f"Error closing database: {e}")

    def __del__(self) -> None:
        """Cleanup on garbage collection."""
        self.close()
