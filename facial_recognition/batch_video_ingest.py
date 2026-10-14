"""Standalone Fast Batch Video Ingestion Engine.

Processes offline/hard-disk video footage (e.g., 3 days of CCTV from an external HDD):
1. Ingests video clips chronologically per camera.
2. Uses intelligent frame sampling (e.g. 2-5 FPS) with fast hardware/CPU grab.
3. Computes exact recorded timestamps for all detections based on clip start time.
4. Matches against enrolled gallery (recognizes known profiles, flags blacklist/watchlist alerts).
5. Writes events directly to local database (SQLite/Postgres) so the dashboard immediately populates with 3 days of analytics.
"""

from __future__ import annotations

import base64
import datetime
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Ensure project root is in sys.path
_current_dir = Path(__file__).resolve().parent
_root_dir = _current_dir.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if str(_root_dir / "backend") not in sys.path:
    sys.path.insert(0, str(_root_dir / "backend"))

from facial_recognition.detector import InsightFaceDetector
from facial_recognition.recognizer import Recognizer
from facial_recognition.video_auditor import VideoAuditor, VideoClipMetadata, extract_camera_id, extract_clip_start_time

logger = logging.getLogger(__name__)


@dataclass
class IngestionProgress:
    """Live progress report for batch video ingestion."""
    running: bool = False
    completed: bool = False
    error: Optional[str] = None
    directory: str = ""
    current_file: str = ""
    current_camera: str = ""
    file_index: int = 0
    total_files: int = 0
    frames_processed: int = 0
    total_estimated_frames: int = 0
    faces_detected: int = 0
    alerts_triggered: int = 0
    progress_percent: float = 0.0
    processing_fps: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    start_time: Optional[float] = None


class BatchVideoIngestEngine:
    """Processes directories of CCTV footage and logs detection timeline events."""

    def __init__(
        self,
        gallery_path: Optional[str] = None,
        sample_fps: float = 3.0,
        threshold: float = 0.60,
        use_gpu: bool = False,
        det_size: Tuple[int, int] = (640, 640),
        database_url: Optional[str] = None,
    ) -> None:
        """
        Args:
            gallery_path: Path to gallery.npz (defaults to known_faces/gallery.npz).
            sample_fps: Target frames per second to sample from video (default: 3.0 FPS for 10x-15x speedup).
            threshold: Face recognition cosine similarity threshold.
            use_gpu: Whether to enable CUDA.
            det_size: Input resolution for InsightFace.
            database_url: Optional override for database URL.
        """
        self.sample_fps = max(0.5, float(sample_fps))
        self.threshold = threshold
        self.use_gpu = use_gpu
        self.det_size = det_size

        if gallery_path is None:
            gallery_path = str(_current_dir / "known_faces" / "gallery.npz")
        self.gallery_path = gallery_path

        self.db_url = database_url
        self.stop_event = threading.Event()
        self.progress = IngestionProgress()
        self._progress_callback: Optional[Callable[[IngestionProgress], None]] = None

        self.detector: Optional[InsightFaceDetector] = None
        self.recognizer: Optional[Recognizer] = None

    def set_progress_callback(self, cb: Callable[[IngestionProgress], None]) -> None:
        """Register a callback for real-time progress updates."""
        self._progress_callback = cb

    def stop(self) -> None:
        """Signal engine to cancel ingestion gracefully."""
        self.stop_event.set()

    def _init_models(self) -> None:
        """Lazy-initialize detector and recognizer."""
        if self.detector is None:
            logger.info("Initializing InsightFaceDetector (det_size=%s)...", self.det_size)
            self.detector = InsightFaceDetector(
                use_gpu=self.use_gpu,
                det_size=self.det_size,
                model_name="buffalo_s",
            )
        if self.recognizer is None:
            logger.info("Initializing Recognizer with gallery: %s...", self.gallery_path)
            self.recognizer = Recognizer(
                gallery_path=self.gallery_path,
                threshold=self.threshold,
            )

    def ingest_directory(
        self,
        footage_dir: str | Path,
        tolerance_seconds: float = 5.0,
    ) -> IngestionProgress:
        """Run batch video ingestion over a directory of CCTV recordings."""
        from database import Base, SessionLocal, engine
        import models

        # Ensure database tables exist
        Base.metadata.create_all(bind=engine)

        self.stop_event.clear()
        self._init_models()
        assert self.detector is not None
        assert self.recognizer is not None

        # 1. Audit and discover all video clips
        auditor = VideoAuditor(tolerance_seconds=tolerance_seconds, compute_full_hashes=False)
        report = auditor.scan_directory(footage_dir)

        clips = report.clips
        # Sort chronologically by start_time
        clips.sort(key=lambda c: c.start_time)

        total_files = len(clips)
        total_est_frames = sum(c.frame_count for c in clips)

        self.progress = IngestionProgress(
            running=True,
            completed=False,
            directory=str(footage_dir),
            total_files=total_files,
            total_estimated_frames=total_est_frames,
            start_time=time.time(),
        )

        if total_files == 0:
            self.progress.running = False
            self.progress.completed = True
            return self.progress

        db = SessionLocal()
        try:
            # Pre-register all discovered cameras so foreign key constraints pass
            discovered_cams = {c.camera_id for c in clips}
            for cam_id in discovered_cams:
                existing_cam = db.query(models.Camera).filter(models.Camera.id == cam_id).first()
                if not existing_cam:
                    new_cam = models.Camera(
                        id=cam_id,
                        name=cam_id.replace("_", " ").title(),
                        zone="Imported Footage",
                        status=models.CameraStatus.online,
                        fps=25.0,
                    )
                    db.add(new_cam)
            db.commit()

            start_t = time.time()
            total_processed_frames = 0
            total_detected_faces = 0
            total_alerts = 0

            # 2. Iterate and process each clip
            for f_idx, clip in enumerate(clips):
                if self.stop_event.is_set():
                    logger.info("Ingestion cancelled by user request.")
                    break

                self.progress.file_index = f_idx + 1
                self.progress.current_file = clip.file_name
                self.progress.current_camera = clip.camera_id
                self._notify_progress()

                processed, detected, alerts = self._process_clip(
                    clip=clip,
                    db=db,
                    models_module=models,
                )

                total_processed_frames += processed
                total_detected_faces += detected
                total_alerts += alerts

                elapsed = time.time() - start_t
                fps_proc = total_processed_frames / elapsed if elapsed > 0 else 0.0

                pct = round(((f_idx + 1) / total_files) * 100.0, 1)
                rem_files = total_files - (f_idx + 1)
                avg_time_per_file = elapsed / (f_idx + 1) if (f_idx + 1) > 0 else 0
                eta = rem_files * avg_time_per_file

                self.progress.frames_processed = total_processed_frames
                self.progress.faces_detected = total_detected_faces
                self.progress.alerts_triggered = total_alerts
                self.progress.progress_percent = pct
                self.progress.processing_fps = round(fps_proc, 1)
                self.progress.elapsed_seconds = round(elapsed, 1)
                self.progress.eta_seconds = round(eta, 1)
                self._notify_progress()

            self.progress.running = False
            self.progress.completed = not self.stop_event.is_set()
            self._notify_progress()
            return self.progress

        except Exception as exc:
            logger.exception("Batch ingestion error: %s", exc)
            self.progress.running = False
            self.progress.error = str(exc)
            self._notify_progress()
            return self.progress
        finally:
            db.close()

    def _process_clip(
        self,
        clip: VideoClipMetadata,
        db: Any,
        models_module: Any,
    ) -> Tuple[int, int, int]:
        """Ingest a single video file, sampling frames at target sample_fps."""
        cap = cv2.VideoCapture(clip.file_path)
        if not cap.isOpened():
            logger.warning("Could not open clip: %s", clip.file_path)
            return 0, 0, 0

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 25.0

        # Calculate frame skip: e.g. 30 fps video with 3 fps sampling => skip 10 frames
        frame_interval = max(1, int(round(fps / self.sample_fps)))
        clip_start_dt = datetime.datetime.fromisoformat(clip.start_time)

        frame_idx = 0
        processed_frames = 0
        detected_faces = 0
        alerts_created = 0

        detections_to_commit = []
        alerts_to_commit = []

        while not self.stop_event.is_set():
            # Quick check if next frame should be sampled
            if frame_idx % frame_interval == 0:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                processed_frames += 1

                # Calculate the exact timestamp this frame was recorded
                frame_time_sec = frame_idx / fps
                frame_dt = clip_start_dt + datetime.timedelta(seconds=frame_time_sec)

                # Run detection
                try:
                    faces = self.detector.detect(frame)
                except Exception as e:
                    logger.debug("Detector error on frame %d: %s", frame_idx, e)
                    faces = []

                for face in faces:
                    detected_faces += 1
                    emb = getattr(face, "embedding", None)
                    bbox = getattr(face, "bbox", [0, 0, 0, 0])
                    gender_raw = getattr(face, "gender", -1)
                    age_raw = getattr(face, "age", 0)

                    # Encode small thumbnail of face
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    h, w = frame.shape[:2]
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    crop = frame[y1:y2, x1:x2]

                    thumb_b64 = None
                    if crop.size > 0:
                        try:
                            # Resize to 112x112 for thumbnail
                            crop_sm = cv2.resize(crop, (112, 112))
                            _, enc = cv2.imencode(".jpg", crop_sm, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                            thumb_b64 = base64.b64encode(enc.tobytes()).decode("utf-8")
                        except Exception:
                            pass

                    # Recognize against gallery
                    profile_id: Optional[str] = None
                    confidence = 0.0
                    status = models_module.DetectionStatus.unknown

                    if emb is not None and emb.size > 0:
                        match_name, match_conf = self.recognizer.match(emb)
                        if match_name is not None:
                            profile_id = match_name
                            confidence = float(match_conf) * 100.0
                            status = models_module.DetectionStatus.recognized

                    # Map gender
                    gender_enum = models_module.Gender.unknown
                    if gender_raw == 1:
                        gender_enum = models_module.Gender.male
                    elif gender_raw == 0:
                        gender_enum = models_module.Gender.female

                    # Look up profile role if recognized
                    is_flagged = False
                    role = models_module.ProfileRole.visitor
                    if profile_id:
                        p_rec = db.query(models_module.Profile).filter(models_module.Profile.id == profile_id).first()
                        if p_rec:
                            role = p_rec.role
                            if role in (models_module.ProfileRole.blacklist, models_module.ProfileRole.watchlist):
                                is_flagged = True
                                status = models_module.DetectionStatus.flagged

                    event_uuid = uuid.uuid4().hex
                    det_record = models_module.Detection(
                        id=event_uuid,
                        event_id=f"evt_{clip.camera_id}_{frame_dt.strftime('%Y%m%d%H%M%S%f')}_{frame_idx}",
                        camera_id=clip.camera_id,
                        profile_id=profile_id,
                        timestamp=frame_dt,
                        status=status,
                        confidence=confidence,
                        age=int(age_raw) if age_raw else None,
                        gender=gender_enum,
                        bbox=json.dumps([int(v) for v in bbox]),
                        face_image=thumb_b64,
                        priority=(
                            models_module.EventPriority.critical
                            if is_flagged
                            else models_module.EventPriority.normal
                        ),
                    )
                    detections_to_commit.append(det_record)

                    # Trigger priority Alert if flagged
                    if is_flagged and profile_id:
                        alerts_created += 1
                        alert_record = models_module.Alert(
                            id=uuid.uuid4().hex,
                            detection_id=event_uuid,
                            profile_id=profile_id,
                            camera_id=clip.camera_id,
                            severity=(
                                models_module.EventPriority.critical
                                if role == models_module.ProfileRole.blacklist
                                else models_module.EventPriority.high
                            ),
                            reason=f"Offline Footage Hit: {profile_id.upper()} ({role.value}) detected on {clip.camera_id}",
                            confidence=confidence,
                            acknowledged=False,
                            created_at=frame_dt,
                        )
                        alerts_to_commit.append(alert_record)

                # Batch flush every 50 detections
                if len(detections_to_commit) >= 50:
                    db.bulk_save_objects(detections_to_commit)
                    if alerts_to_commit:
                        db.bulk_save_objects(alerts_to_commit)
                    db.commit()
                    detections_to_commit.clear()
                    alerts_to_commit.clear()

            else:
                # Fast forward: grab frame without decoding pixels
                ret = cap.grab()
                if not ret:
                    break

            frame_idx += 1

        cap.release()

        # Flush remaining records
        if detections_to_commit:
            db.bulk_save_objects(detections_to_commit)
        if alerts_to_commit:
            db.bulk_save_objects(alerts_to_commit)
        db.commit()

        return processed_frames, detected_faces, alerts_created

    def _notify_progress(self) -> None:
        """Invoke progress callback if registered."""
        if self._progress_callback:
            try:
                self._progress_callback(self.progress)
            except Exception:
                pass


# Global singleton instance for background API tasks
_global_engine: Optional[BatchVideoIngestEngine] = None
_global_engine_lock = threading.Lock()


def get_global_ingest_engine() -> BatchVideoIngestEngine:
    global _global_engine
    with _global_engine_lock:
        if _global_engine is None:
            _global_engine = BatchVideoIngestEngine()
        return _global_engine


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Standalone Fast Batch Video Ingest Engine")
    parser.add_argument("--dir", required=True, help="Path to CCTV video directory")
    parser.add_argument("--sample-fps", type=float, default=3.0, help="Frames per second to sample (default: 3.0)")
    parser.add_argument("--threshold", type=float, default=0.60, help="Recognition threshold (default: 0.60)")
    parser.add_argument("--use-gpu", action="store_true", help="Enable GPU inference")
    args = parser.parse_args()

    engine_instance = BatchVideoIngestEngine(
        sample_fps=args.sample_fps,
        threshold=args.threshold,
        use_gpu=args.use_gpu,
    )

    print(f"[*] Starting Standalone Batch Ingestion on: {args.dir}")
    print(f"    - Frame Sampling: {args.sample_fps} FPS")
    print(f"    - Recognition Threshold: {args.threshold}")

    def on_prog(p: IngestionProgress) -> None:
        if p.total_files > 0:
            print(
                f"\r[Progress: {p.progress_percent:.1f}%] "
                f"File {p.file_index}/{p.total_files} ({p.current_file}) | "
                f"Frames: {p.frames_processed} | Faces: {p.faces_detected} | "
                f"Alerts: {p.alerts_triggered} | Speed: {p.processing_fps} FPS | ETA: {p.eta_seconds:.0f}s",
                end="",
                flush=True,
            )

    engine_instance.set_progress_callback(on_prog)
    res = engine_instance.ingest_directory(args.dir)

    print("\n\n[+] Ingestion Finished!")
    print(f"    - Completed: {res.completed}")
    print(f"    - Total Files: {res.total_files}")
    print(f"    - Total Frames Processed: {res.frames_processed}")
    print(f"    - Total Faces Detected: {res.faces_detected}")
    print(f"    - Priority Alerts Created: {res.alerts_triggered}")
    print(f"    - Elapsed Time: {res.elapsed_seconds}s")
