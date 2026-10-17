
from fastapi import APIRouter, File, UploadFile, Form, Depends, Query, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import uuid
import json

from database import get_db
from models import *
from models import ModelThreshold as DBModelThreshold
from schemas import *
from config import settings, IST
from dependencies import verify_edge_node
from state import active_version_bundle, node_health_store
from websocket import manager

router = APIRouter(tags=['System'])



# ==================== Health Check ====================

@router.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(IST).isoformat()}





# ==================== KPI Endpoints ====================

@router.get("/api/kpis", response_model=SystemKpisResponse)
def get_kpis(
    source: Optional[str] = Query(None, description="Filter by data source: 'live' or 'archive'"),
    batch_id: Optional[str] = Query(None, description="Filter by specific archive batch ID"),
    db: Session = Depends(get_db)
):
    """Get system KPIs, optionally filtered by source or batch."""
    today = datetime.now(IST).date()
    
    det_q = db.query(Detection)
    alert_q = db.query(Alert)
    
    if source:
        det_q = det_q.filter(Detection.source == source)
        alert_q = alert_q.filter(Alert.source == source)
    if batch_id:
        det_q = det_q.filter(Detection.batch_id == batch_id)
        alert_q = alert_q.filter(Alert.batch_id == batch_id)
        
    total_detections = det_q.with_entities(func.count(Detection.id)).scalar() or 0
    unique_profiles = det_q.with_entities(func.count(func.distinct(Detection.profile_id))).scalar() or 0
    total_profiles = db.query(func.count(Profile.id)).scalar() or 0
    cameras_online = db.query(func.count(Camera.id)).filter(
        Camera.status == CameraStatus.online
    ).scalar() or 0
    critical_alerts = alert_q.filter(
        Alert.severity == "critical",
        Alert.acknowledged == False
    ).with_entities(func.count(Alert.id)).scalar() or 0
    
    # Today's stats evaluated against local day start
    today_start_ist = datetime.combine(today, datetime.min.time()).replace(tzinfo=IST)
    
    recognitions_today = det_q.filter(
        Detection.timestamp >= today_start_ist,
        Detection.status == DetectionStatus.recognized
    ).with_entities(func.count(Detection.id)).scalar() or 0
    unknowns_today = det_q.filter(
        Detection.timestamp >= today_start_ist,
        Detection.status == DetectionStatus.unknown
    ).with_entities(func.count(Detection.id)).scalar() or 0
    
    # Average confidence
    avg_confidence = det_q.filter(
        Detection.confidence > 0
    ).with_entities(func.avg(Detection.confidence)).scalar() or 0.0
    
    return SystemKpisResponse(
        total_detections=total_detections,
        unique_individuals=unique_profiles or 0,
        total_profiles=total_profiles,
        cameras_online=cameras_online,
        critical_alerts=critical_alerts,
        recognitions_today=recognitions_today,
        unknowns_today=unknowns_today,
        average_confidence=float(avg_confidence),
    )





# ==================== System Version Bundle Endpoint ====================

@router.get("/api/system/version-bundle", response_model=VersionBundleResponse)
def get_system_version_bundle():
    """
    Get current immutable version snapshot for detection model, embedding model,
    gallery, thresholds, camera configuration, and algorithm versions.
    """
    return active_version_bundle.to_dict()




@router.post("/api/nodes/health", response_model=NodeHealthReportResponse)
def report_node_health(
    req: NodeHealthReportRequest,
    api_key: str = Depends(verify_edge_node)
):
    """
    Ingest live health metrics, operational mode, and adaptive runtime decisions
    from an edge recognition node.
    """
    now = datetime.now(IST)
    node_health_store[req.device_id] = {
        "device_id": req.device_id,
        "camera_id": req.camera_id,
        "mode": req.mode,
        "metrics": req.metrics,
        "decisions": req.decisions or [],
        "last_heartbeat": now.isoformat(),
    }
    return NodeHealthReportResponse(
        status="ok",
        recorded_at=now,
    )





@router.get("/api/nodes/health")
def get_all_nodes_health(
    db: Session = Depends(get_db)
):
    """Get latest health snapshots and runtime modes for all active edge nodes."""
    return {"nodes": list(node_health_store.values())}




# ==================== Thresholds Endpoints ====================

@router.get("/api/thresholds", response_model=ModelThresholdsResponse)
def get_thresholds(db: Session = Depends(get_db)):
    """Get current model thresholds."""
    # Defaults
    thresholds = {
        "similarity_confidence": 0.60,
        "liveness_threshold": 0.50,
        "age_variance": 5.0,
    }
    
    # Load from DB if available
    db_thresholds = db.query(DBModelThreshold).all()
    for t in db_thresholds:
        if t.name in thresholds:
            thresholds[t.name] = t.value
    
    return ModelThresholdsResponse(**thresholds)





@router.post("/api/thresholds", response_model=ModelThresholdsResponse)
def update_thresholds(
    thresholds: ModelThresholdsResponse,
    db: Session = Depends(get_db)
):
    """Update model thresholds."""
    for field, value in thresholds.dict().items():
        existing = db.query(DBModelThreshold).filter(DBModelThreshold.name == field).first()
        if existing:
            existing.value = value
        else:
            db.add(DBModelThreshold(id=field, name=field, value=value))
    
    db.commit()
    
    # Broadcast to all connected clients
    import asyncio
    asyncio.create_task(
        manager.broadcast("kpis", {"thresholds": thresholds.dict()})
    )
    
    return thresholds


