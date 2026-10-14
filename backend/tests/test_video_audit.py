"""Tests for CCTV Video Audit & Standalone Batch Ingestion."""

import os
import tempfile
from pathlib import Path
import cv2
import numpy as np
import pytest
from starlette.testclient import TestClient

from main import app
from auth import create_access_token
from facial_recognition.video_auditor import VideoAuditor, format_seconds, extract_clip_start_time


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_video_dir():
    """Create a temporary directory containing 2 synthetic test video clips with known timestamps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cam_dir = tmp_path / "Camera_01"
        cam_dir.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        # Clip 1: 2026-10-10 10:00:00 (10 frames at 10 fps = 1.0 second duration, ends 10:00:01)
        clip1_path = cam_dir / "CAM01_2026-10-10_10-00-00.mp4"
        out1 = cv2.VideoWriter(str(clip1_path), fourcc, 10.0, (160, 120))
        for _ in range(10):
            frame = np.zeros((120, 160, 3), dtype=np.uint8)
            out1.write(frame)
        out1.release()

        # Clip 2: 2026-10-10 10:00:15 (starts at 10:00:15 => gap of 14 seconds between 10:00:01 and 10:00:15)
        clip2_path = cam_dir / "CAM01_2026-10-10_10-00-15.mp4"
        out2 = cv2.VideoWriter(str(clip2_path), fourcc, 10.0, (160, 120))
        for _ in range(10):
            frame = np.zeros((120, 160, 3), dtype=np.uint8)
            out2.write(frame)
        out2.release()

        yield tmpdir


def test_format_seconds():
    assert format_seconds(45) == "45s"
    assert format_seconds(125) == "2m 5s"
    assert format_seconds(3665) == "1h 1m 5s"


def test_video_auditor_gap_detection(sample_video_dir):
    auditor = VideoAuditor(tolerance_seconds=3.0)
    report = auditor.scan_directory(sample_video_dir)

    assert report.total_files_scanned == 2
    assert report.total_cameras == 1
    assert len(report.clips) == 2
    assert len(report.gaps) == 1

    gap = report.gaps[0]
    assert gap.camera_id == "Camera_01"
    assert gap.gap_duration_seconds >= 13.0
    assert gap.severity in ("SUSPICIOUS_CUT", "BUFFER_HITCH", "CRITICAL_BLACKOUT")
    assert report.security_verdict in ("SECURITY_WARNING_TIMELINE_GAPS", "HIGH_SECURITY_ALERT_MISSING_FOOTAGE")


def test_api_scan_cctv_footage(client, auth_headers, sample_video_dir):
    res = client.post(
        "/api/video-audit/scan",
        json={"directory": sample_video_dir, "tolerance_seconds": 3.0, "compute_hashes": True},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_files_scanned"] == 2
    assert data["total_gaps_detected"] == 1
    assert "Camera_01" in [c["camera_id"] for c in data["cameras_summary"]]

    # Fetch latest report endpoint
    rep_res = client.get("/api/video-audit/latest-report", headers=auth_headers)
    assert rep_res.status_code == 200
    assert rep_res.json()["total_files_scanned"] == 2


def test_api_scan_nonexistent_directory(client, auth_headers):
    res = client.post(
        "/api/video-audit/scan",
        json={"directory": "Z:/NonExistentDrive/Footage", "tolerance_seconds": 5.0},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_api_ingest_status_and_stop(client, auth_headers):
    res = client.get("/api/video-audit/status", headers=auth_headers)
    assert res.status_code == 200
    status = res.json()
    assert "running" in status
    assert "progress_percent" in status

    stop_res = client.post("/api/video-audit/stop", headers=auth_headers)
    assert stop_res.status_code == 200


def test_video_auditor_nan_sanitization(monkeypatch, sample_video_dir):
    """Verify auditor does not crash when container returns NaN/Inf for FPS or frames."""
    import math

    class MockVideoCapture:
        def __init__(self, path):
            self.opened = True
        def isOpened(self):
            return self.opened
        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS:
                return float("nan")
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return float("inf")
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return 640
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return 480
            return 0
        def read(self):
            # Returns a valid frame
            return True, np.zeros((480, 640, 3), dtype=np.uint8)
        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", MockVideoCapture)
    auditor = VideoAuditor(tolerance_seconds=3.0)
    report = auditor.scan_directory(sample_video_dir)

    assert report.total_files_scanned == 2
    for clip in report.clips:
        assert not math.isnan(clip.fps)
        assert not math.isinf(clip.fps)
        assert not math.isnan(clip.duration_seconds)
        assert not math.isinf(clip.duration_seconds)


def test_video_auditor_timeline_overlap_collision():
    """Verify that overlapping clips (spliced/backdated video) trigger timeline collision alert."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cam_dir = Path(tmpdir) / "cam_lobby"
        cam_dir.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        # Clip 1: Starts at 10:00:00, 10 frames at 1.0 fps => duration 10.0s, ends at 10:00:10
        c1 = cam_dir / "CAM01_2026-10-10_10-00-00.mp4"
        out1 = cv2.VideoWriter(str(c1), fourcc, 1.0, (160, 120))
        for _ in range(10):
            out1.write(np.zeros((120, 160, 3), dtype=np.uint8))
        out1.release()

        # Clip 2: Starts at 10:00:05 (starts 5 seconds BEFORE Clip 1 ends => 5s collision!)
        c2 = cam_dir / "CAM01_2026-10-10_10-00-05.mp4"
        out2 = cv2.VideoWriter(str(c2), fourcc, 1.0, (160, 120))
        for _ in range(10):
            out2.write(np.zeros((120, 160, 3), dtype=np.uint8))
        out2.release()

        auditor = VideoAuditor(tolerance_seconds=2.0)
        report = auditor.scan_directory(tmpdir)

        assert report.total_files_scanned == 2
        assert len(report.gaps) == 1
        collision = report.gaps[0]
        assert collision.severity == "TIMELINE_OVERLAP_COLLISION"
        assert collision.tamper_risk == "HIGH"
        assert "overlap" in collision.formatted_duration
        assert report.security_verdict == "HIGH_SECURITY_ALERT_TIMELINE_COLLISION"


def test_video_auditor_scan_file(sample_video_dir):
    """Verify single-file audit method inspects a single clip accurately."""
    sample_files = list(Path(sample_video_dir).rglob("*.mp4"))
    assert len(sample_files) >= 1
    target_file = sample_files[0]

    auditor = VideoAuditor(tolerance_seconds=3.0)
    report = auditor.scan_file(target_file)

    assert report.total_files_scanned == 1
    assert report.total_cameras == 1
    assert len(report.clips) == 1
    assert report.total_footage_duration_seconds > 0.0
    assert report.security_verdict in ("SECURE_100_PERCENT_CONTINUOUS", "WARNING_SUSPICIOUS_CLIPS_DETECTED")


def test_api_scan_root_drive_blocked(client, auth_headers):
    """Verify API prevents DoS by blocking raw drive root scans."""
    for root_candidate in ("C:\\", "D:\\", "C:"):
        res = client.post(
            "/api/video-audit/scan",
            json={"directory": root_candidate, "tolerance_seconds": 5.0},
            headers=auth_headers,
        )
        assert res.status_code == 400
        assert "restricted" in res.json()["detail"].lower()


def test_api_scan_single_file(client, auth_headers, sample_video_dir):
    """Verify API correctly processes a single video file path."""
    sample_files = list(Path(sample_video_dir).rglob("*.mp4"))
    assert len(sample_files) >= 1
    target_file = str(sample_files[0])

    res = client.post(
        "/api/video-audit/scan",
        json={"directory": target_file, "tolerance_seconds": 3.0},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_files_scanned"] == 1
    assert data["total_cameras"] == 1


def test_compute_sha256_head_mid_tail():
    """Verify head-mid-tail block sampling for fast hashing of large files."""
    from facial_recognition.video_auditor import compute_sha256
    with tempfile.NamedTemporaryFile(delete=False) as f:
        # Create a 6MB file
        f.write(b"A" * (2 * 1024 * 1024))
        f.write(b"B" * (2 * 1024 * 1024))
        f.write(b"C" * (2 * 1024 * 1024))
        path = Path(f.name)

    try:
        h1 = compute_sha256(path, max_bytes=3 * 1024 * 1024)
        assert len(h1) == 64

        # Tamper the middle block
        with path.open("r+b") as f:
            f.seek(3 * 1024 * 1024)
            f.write(b"Z" * 1024)

        h2 = compute_sha256(path, max_bytes=3 * 1024 * 1024)
        assert h1 != h2, "Head-mid-tail sampling must detect tampering in the middle block"
    finally:
        if path.exists():
            path.unlink()


def test_api_ingest_root_drive_blocked(client, auth_headers):
    """Verify API prevents DoS by blocking raw drive root ingestion."""
    for root_candidate in ("C:\\", "D:\\", "/"):
        res = client.post(
            "/api/video-audit/ingest",
            json={"directory": root_candidate},
            headers=auth_headers,
        )
        assert res.status_code == 400
        assert "restricted" in res.json()["detail"].lower()




