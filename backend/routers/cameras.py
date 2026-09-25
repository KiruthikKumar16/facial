import uuid
import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, File, UploadFile, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Camera, CameraConfig, CameraStatus as CameraStatusEnum
from schemas import (
    CameraResponse, CameraConfigResponse, CameraConfigUpdateRequest,
    CameraConfigRollbackRequest, CameraConfigHistoryResponse
)
from config import IST

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Cameras"])

@router.get("/api/cameras", response_model=list[CameraResponse])
def get_cameras(db: Session = Depends(get_db)):
    """Get all cameras with health status."""
    cameras = db.query(Camera).all()
    return [CameraResponse.model_validate(c) for c in cameras]


@router.get("/api/cameras/{camera_id}/config", response_model=CameraConfigResponse)
def get_camera_config(camera_id: str, db: Session = Depends(get_db)):
    """Get active recognition configuration for a specific camera."""
    # Ensure camera exists
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        camera = Camera(id=camera_id, name=camera_id, status=CameraStatusEnum.online)
        db.add(camera)
        db.commit()

    config = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera_id,
        CameraConfig.is_active == True
    ).order_by(CameraConfig.version.desc()).first()

    if not config:
        # Create default initial config (version 1)
        config = CameraConfig(
            id=str(uuid.uuid4()),
            camera_id=camera_id,
            version=1,
            is_active=True,
            detection_threshold=0.50,
            recognition_threshold=0.35,
            quality_thresholds=None,
            sampling_rate=1,
            temporal_window=3.0,
            notes="Initial default configuration",
            created_at=datetime.now(IST)
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    return CameraConfigResponse.model_validate(config)


@router.post("/api/cameras/{camera_id}/config", response_model=CameraConfigResponse)
@router.put("/api/cameras/{camera_id}/config", response_model=CameraConfigResponse)
def update_camera_config(
    camera_id: str,
    req: CameraConfigUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new version of recognition configuration for a camera.
    Deactivates older versions and activates the new version.
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        camera = Camera(id=camera_id, name=camera_id, status=CameraStatusEnum.online)
        db.add(camera)
        db.commit()

    # Get latest version number
    latest = db.query(CameraConfig).filter(CameraConfig.camera_id == camera_id).order_by(CameraConfig.version.desc()).first()
    next_version = (latest.version + 1) if latest else 1

    # Deactivate current active configs
    db.query(CameraConfig).filter(CameraConfig.camera_id == camera_id, CameraConfig.is_active == True).update({"is_active": False})

    # Serialize quality_thresholds
    q_str = json.dumps(req.quality_thresholds) if req.quality_thresholds is not None else (latest.quality_thresholds if latest else None)

    new_config = CameraConfig(
        id=str(uuid.uuid4()),
        camera_id=camera_id,
        version=next_version,
        is_active=True,
        detection_threshold=req.detection_threshold if req.detection_threshold is not None else (latest.detection_threshold if latest else 0.50),
        recognition_threshold=req.recognition_threshold if req.recognition_threshold is not None else (latest.recognition_threshold if latest else 0.35),
        quality_thresholds=q_str,
        sampling_rate=req.sampling_rate if req.sampling_rate is not None else (latest.sampling_rate if latest else 1),
        temporal_window=req.temporal_window if req.temporal_window is not None else (latest.temporal_window if latest else 3.0),
        notes=req.notes or f"Updated to version {next_version}",
        created_at=datetime.now(IST)
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    logger.info(f"Camera {camera_id} configuration updated to version {next_version}")
    return CameraConfigResponse.model_validate(new_config)


@router.post("/api/cameras/{camera_id}/config/rollback/{version}", response_model=CameraConfigResponse)
def rollback_camera_config_path(
    camera_id: str,
    version: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return _execute_rollback(camera_id, version, notes, db)


@router.post("/api/cameras/{camera_id}/config/rollback", response_model=CameraConfigResponse)
def rollback_camera_config_body(
    camera_id: str,
    payload: CameraConfigRollbackRequest,
    db: Session = Depends(get_db)
):
    return _execute_rollback(camera_id, payload.target_version, payload.notes, db)


def _execute_rollback(camera_id: str, version: int, notes: Optional[str], db: Session):
    """
    Rollback camera configuration to a target historical version.
    Creates a new active version copying parameters from target version.
    """
    target = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera_id,
        CameraConfig.version == version
    ).first()

    if not target:
        raise HTTPException(status_code=404, detail=f"Configuration version {version} not found for camera {camera_id}")

    latest = db.query(CameraConfig).filter(CameraConfig.camera_id == camera_id).order_by(CameraConfig.version.desc()).first()
    next_version = (latest.version + 1) if latest else 1

    # Deactivate current active
    db.query(CameraConfig).filter(CameraConfig.camera_id == camera_id, CameraConfig.is_active == True).update({"is_active": False})

    rollback_config = CameraConfig(
        id=str(uuid.uuid4()),
        camera_id=camera_id,
        version=next_version,
        is_active=True,
        detection_threshold=target.detection_threshold,
        recognition_threshold=target.recognition_threshold,
        quality_thresholds=target.quality_thresholds,
        sampling_rate=target.sampling_rate,
        temporal_window=target.temporal_window,
        notes=notes or f"Rollback to version {version}",
        created_at=datetime.now(IST)
    )
    db.add(rollback_config)
    db.commit()
    db.refresh(rollback_config)

    logger.info(f"Camera {camera_id} rolled back to parameters of v{version} as new v{next_version}")
    return CameraConfigResponse.model_validate(rollback_config)


@router.get("/api/cameras/{camera_id}/config/history", response_model=CameraConfigHistoryResponse)
def get_camera_config_history(camera_id: str, db: Session = Depends(get_db)):
    """Get full configuration audit history for a camera."""
    configs = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera_id
    ).order_by(CameraConfig.version.desc()).all()

    active = next((c.version for c in configs if c.is_active), 1)

    return CameraConfigHistoryResponse(
        camera_id=camera_id,
        active_version=active,
        history=[CameraConfigResponse.model_validate(c) for c in configs]
    )


from dependencies import verify_edge_node
@router.get("/api/internal/camera_configs", response_model=List[CameraConfigResponse])
def get_all_active_camera_configs(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """Bulk sync endpoint for edge nodes to fetch active configurations for all cameras."""
    configs = db.query(CameraConfig).filter(CameraConfig.is_active == True).all()
    return [CameraConfigResponse.model_validate(c) for c in configs]
