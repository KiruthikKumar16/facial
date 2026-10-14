"""CCTV Video Integrity & Batch Ingestion Router.

Provides API endpoints for:
1. Scanning offline/hard-disk CCTV footage for missing intervals, gaps, and trimmed clips.
2. Generating security timeline continuity reports and chain-of-custody manifests.
3. Initiating fast batch face recognition ingestion on offline footage.
4. Monitoring live ingestion progress.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from facial_recognition.batch_video_ingest import get_global_ingest_engine, IngestionProgress
from facial_recognition.video_auditor import VideoAuditor, VideoAuditReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-audit", tags=["Video Audit & Ingestion"])

# Cache for latest audit report in memory
_latest_audit_report: Optional[Dict[str, Any]] = None
_audit_lock = threading.Lock()
_ingestion_thread: Optional[threading.Thread] = None


class ScanRequest(BaseModel):
    directory: str = Field(..., description="Absolute path to CCTV footage directory or hard drive")
    tolerance_seconds: float = Field(5.0, description="Allowable gap in seconds before flagging as missing footage")
    compute_hashes: bool = Field(True, description="Whether to compute SHA-256 for chain of custody")


class IngestRequest(BaseModel):
    directory: str = Field(..., description="Absolute path to CCTV footage directory or hard drive")
    sample_fps: float = Field(3.0, description="Frames per second to sample (default: 3.0 FPS for fast 10-15x scan)")
    threshold: float = Field(0.60, description="Face recognition confidence threshold")
    use_gpu: bool = Field(False, description="Enable GPU acceleration if available")


@router.post("/scan", response_model=Dict[str, Any])
def scan_cctv_footage(req: ScanRequest):
    """
    Perform deep timeline continuity & tamper analysis on CCTV directory.
    Identifies missing time clips, abnormally trimmed videos, and computes SHA-256 hashes.
    """
    global _latest_audit_report
    target_path = Path(req.directory)
    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory does not exist: {req.directory}",
        )

    try:
        auditor = VideoAuditor(
            tolerance_seconds=req.tolerance_seconds,
            compute_full_hashes=req.compute_hashes,
        )
        report: VideoAuditReport = auditor.scan_directory(target_path)
        report_dict = asdict(report)

        with _audit_lock:
            _latest_audit_report = report_dict

        return report_dict
    except Exception as exc:
        logger.exception("Error scanning CCTV footage: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit scan failed: {str(exc)}",
        )


@router.get("/latest-report", response_model=Dict[str, Any])
def get_latest_audit_report():
    """Retrieve the latest cached CCTV security audit report."""
    with _audit_lock:
        if _latest_audit_report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No audit report available. Run a scan first.",
            )
        return _latest_audit_report


@router.post("/ingest", response_model=Dict[str, Any])
def start_batch_ingest(req: IngestRequest):
    """
    Start standalone fast batch video ingestion in a background thread.
    Processes video clips chronologically, computes exact recorded timestamps,
    and populates detections, alerts, and demographics into the database.
    """
    global _ingestion_thread
    target_path = Path(req.directory)
    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory does not exist: {req.directory}",
        )

    engine = get_global_ingest_engine()
    if engine.progress.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Batch video ingestion is already currently running.",
        )

    # Configure engine
    engine.sample_fps = max(0.5, req.sample_fps)
    engine.threshold = req.threshold
    engine.use_gpu = req.use_gpu

    def _worker():
        try:
            logger.info("Starting background batch ingestion on %s...", req.directory)
            engine.ingest_directory(target_path)
            logger.info("Background batch ingestion completed.")
        except Exception as exc:
            logger.exception("Background ingestion worker failed: %s", exc)

    _ingestion_thread = threading.Thread(target=_worker, daemon=True)
    _ingestion_thread.start()

    return {
        "status": "started",
        "directory": str(target_path),
        "sample_fps": req.sample_fps,
        "threshold": req.threshold,
    }


@router.get("/status", response_model=Dict[str, Any])
def get_ingest_status():
    """Get live batch ingestion progress, processing speed, ETA, and detection counts."""
    engine = get_global_ingest_engine()
    p: IngestionProgress = engine.progress
    return asdict(p)


@router.post("/stop", response_model=Dict[str, Any])
def stop_batch_ingest():
    """Gracefully cancel the running batch ingestion worker."""
    engine = get_global_ingest_engine()
    if not engine.progress.running:
        return {"status": "not_running"}

    engine.stop()
    return {"status": "stopping"}
