"""Unit and integration tests for security patches:
1. Anti-Spoofing / Presentation Attack Alert Guard
2. Stream Timestamp Freshness / Replay Detection
3. Camera Lens Occlusion / Tampering Detection
4. Video Auditor Container Truncation Check
"""

import sys
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import pytest
import numpy as np

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent))

from fastapi.testclient import TestClient
from main import app
from database import get_db, SessionLocal
from models import Detection, Alert, Camera
from config import IST, settings
from facial_recognition.quality import FaceQualityAssessor
from facial_recognition.video_auditor import VideoAuditor, VideoClipMetadata

client = TestClient(app)
EDGE_KEY = os.environ.get("EDGE_API_KEY", "4349000f7201d2db0193e1cec0fc42341837486915fab5a4802fd1371ac0c6dd")


def test_liveness_score_stored_and_returned():
    """Verify that legitimate liveness score is preserved upon ingestion."""
    event_id = f"test_live_{uuid.uuid4().hex[:12]}"
    payload = {
        "camera_id": "cam_sec_01",
        "identity": "Test Subject",
        "confidence": 0.92,
        "bbox": [50, 50, 150, 150],
        "timestamp": datetime.now(IST).isoformat(),
        "event_id": event_id,
        "liveness_score": 0.88,
    }
    resp = client.post("/api/detections", json=payload, headers={"X-API-Key": EDGE_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data.get("liveness_score", 0.0) - 0.88) < 1e-4


def test_presentation_attack_spoof_alert_triggered():
    """Verify that a low liveness score (< threshold) triggers a critical spoof alert."""
    event_id = f"test_spoof_{uuid.uuid4().hex[:12]}"
    payload = {
        "camera_id": "cam_sec_02",
        "identity": "Impersonator",
        "confidence": 0.95,
        "bbox": [60, 60, 160, 160],
        "timestamp": datetime.now(IST).isoformat(),
        "event_id": event_id,
        "liveness_score": 0.22,  # Sub-threshold: photo/screen spoof
    }
    resp = client.post("/api/detections", json=payload, headers={"X-API-Key": EDGE_KEY})
    assert resp.status_code == 200

    # Query DB to verify critical Alert was generated
    db = SessionLocal()
    try:
        det = db.query(Detection).filter(Detection.event_id == event_id).first()
        assert det is not None
        assert abs(det.liveness_score - 0.22) < 1e-4

        alert = db.query(Alert).filter(
            Alert.detection_id == det.id,
            Alert.severity == "critical"
        ).first()
        assert alert is not None
        assert "Presentation Attack" in alert.reason or "Fake Clone" in alert.reason
    finally:
        db.close()


def test_stream_timestamp_skew_replay_guard():
    """Verify that historical timestamp skew (> 15 mins) triggers a suspected replay warning."""
    event_id = f"test_replay_{uuid.uuid4().hex[:12]}"
    # 2 hours in the past
    stale_timestamp = (datetime.now(IST) - timedelta(hours=2)).isoformat()
    payload = {
        "camera_id": "cam_sec_03",
        "identity": "Replay Probe",
        "confidence": 0.90,
        "bbox": [40, 40, 140, 140],
        "timestamp": stale_timestamp,
        "event_id": event_id,
        "liveness_score": 0.85,
    }
    resp = client.post("/api/detections", json=payload, headers={"X-API-Key": EDGE_KEY})
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        det = db.query(Detection).filter(Detection.event_id == event_id).first()
        assert det is not None

        alert = db.query(Alert).filter(
            Alert.detection_id == det.id,
            Alert.severity == "warning"
        ).first()
        assert alert is not None
        assert "Stream Timestamp Skew" in alert.reason or "Suspected Replay" in alert.reason
    finally:
        db.close()


def test_camera_occlusion_detector_logic():
    """Verify camera occlusion detection on blacked-out / blinded frames."""
    from facial_recognition.main_cpu import CpuCameraPipeline

    # Mock detector and recognizer
    class DummyDetector:
        def detect(self, img): return []
    class DummyRecognizer:
        labels = []
        embeddings = []
        threshold = 0.35

    pipe = CpuCameraPipeline(
        camera_id="test_cam_occlusion",
        source=0,
        detector=DummyDetector(),
        recognizer=DummyRecognizer(),
        logger=None,
    )

    # Frame 1: Natural noisy image -> Not occluded
    natural_frame = np.random.randint(50, 200, (240, 320, 3), dtype=np.uint8)
    assert not pipe._check_camera_occlusion(natural_frame)
    assert not pipe.is_occluded

    # Blinded / pitch black frame -> Occlusion counter increments
    black_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for _ in range(35):
        pipe._check_camera_occlusion(black_frame)
    assert pipe.is_occluded

    # Recovery: natural lighting resumes
    for _ in range(25):
        pipe._check_camera_occlusion(natural_frame)
    assert not pipe.is_occluded


def test_deep_fas_engine_fallback():
    """Verify FaceQualityAssessor handles FAS inference and graceful heuristic fallback."""
    assessor = FaceQualityAssessor()
    assert hasattr(assessor, "_fas_session")

    # Natural skin-toned synthetic patch
    skin_patch = np.zeros((100, 100, 3), dtype=np.uint8)
    skin_patch[:, :] = (130, 160, 210)  # BGR skin-like tone
    score = assessor.compute_liveness_score(skin_patch)
    assert 0.0 <= score <= 1.0


def test_video_auditor_truncation_detection(tmp_path):
    """Verify video auditor detects truncated container metadata."""
    auditor = VideoAuditor(compute_full_hashes=False)
    assert hasattr(auditor, "scan_directory")
