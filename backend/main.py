"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func

from config import settings
from database import Base, engine, get_db
from models import (
    Camera, Profile, Detection, Alert, ModelThreshold,
    DetectionStatus as DetectionStatusEnum, CameraStatus as CameraStatusEnum
)
from schemas import (
    CameraResponse, ProfileResponse, DetectionResponse, FaceLogResponse,
    AlertResponse, SystemKpisResponse, ModelThresholdsResponse,
    ForensicMatchResponse, AttendanceRecordResponse
)
from websocket import manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    # Startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ==================== Health Check ====================

@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ==================== KPI Endpoints ====================

@app.get("/api/kpis", response_model=SystemKpisResponse)
def get_kpis(db: Session = Depends(get_db)):
    """Get system KPIs."""
    today = datetime.utcnow().date()
    
    total_detections = db.query(func.count(Detection.id)).scalar() or 0
    unique_profiles = db.query(func.count(func.distinct(Detection.profile_id))).scalar() or 0
    total_profiles = db.query(func.count(Profile.id)).scalar() or 0
    cameras_online = db.query(func.count(Camera.id)).filter(
        Camera.status == CameraStatusEnum.online
    ).scalar() or 0
    critical_alerts = db.query(func.count(Alert.id)).filter(
        Alert.severity == "critical",
        Alert.acknowledged == False
    ).scalar() or 0
    
    # Today's stats
    today_start = datetime.combine(today, datetime.min.time())
    recognitions_today = db.query(func.count(Detection.id)).filter(
        Detection.timestamp >= today_start,
        Detection.status == DetectionStatusEnum.recognized
    ).scalar() or 0
    unknowns_today = db.query(func.count(Detection.id)).filter(
        Detection.timestamp >= today_start,
        Detection.status == DetectionStatusEnum.unknown
    ).scalar() or 0
    
    # Average confidence
    avg_confidence = db.query(func.avg(Detection.confidence)).filter(
        Detection.confidence > 0
    ).scalar() or 0.0
    
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


# ==================== Camera Endpoints ====================

@app.get("/api/cameras", response_model=list[CameraResponse])
def get_cameras(db: Session = Depends(get_db)):
    """Get all cameras with health status."""
    cameras = db.query(Camera).all()
    return [CameraResponse.from_orm(c) for c in cameras]


# ==================== Profile Endpoints ====================

@app.get("/api/profiles", response_model=list[ProfileResponse])
def get_profiles(db: Session = Depends(get_db)):
    """Get all profiles."""
    profiles = db.query(Profile).all()
    return [ProfileResponse.from_orm(p) for p in profiles]


@app.get("/api/profiles/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    """Get a specific profile."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return {"detail": "Profile not found"}
    return ProfileResponse.from_orm(profile)


# ==================== Detection/Log Endpoints ====================

@app.get("/api/logs", response_model=list[FaceLogResponse])
def get_logs(
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get face detection logs."""
    detections = db.query(Detection).order_by(
        Detection.timestamp.desc()
    ).limit(limit).offset(offset).all()
    
    results = []
    tones = ['sky', 'amber', 'rose', 'violet', 'emerald', 'cyan', 'orange', 'indigo']
    
    for i, det in enumerate(detections):
        results.append(FaceLogResponse(
            id=det.id,
            camera_id=det.camera_id,
            camera_name=det.camera.name if det.camera else "Unknown",
            timestamp=det.timestamp.isoformat(),
            status=det.status.value,
            confidence=det.confidence,
            liveness_score=det.liveness_score,
            profile_id=det.profile_id,
            profile_name=det.profile.name if det.profile else None,
            role=det.profile.role.value if det.profile else None,
            age=det.age or 0,
            gender=det.gender.value if det.gender else "unknown",
            wearing_mask=det.wearing_mask,
            wearing_glasses=det.wearing_glasses,
            snapshot_tone=tones[i % len(tones)],
        ))
    
    return results


# ==================== Alert Endpoints ====================

@app.get("/api/alerts", response_model=list[AlertResponse])
def get_alerts(
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db)
):
    """Get recent alerts."""
    alerts = db.query(Alert).order_by(
        Alert.timestamp.desc()
    ).limit(limit).all()
    
    results = []
    tones = ['sky', 'amber', 'rose', 'violet', 'emerald', 'cyan', 'orange', 'indigo']
    
    for i, alert in enumerate(alerts):
        results.append(AlertResponse(
            id=alert.id,
            log_id=alert.detection_id or "",
            camera_id=alert.camera_id,
            camera_name=alert.camera.name if alert.camera else "Unknown",
            timestamp=alert.timestamp.isoformat(),
            severity=alert.severity,
            reason=alert.reason,
            profile_id=alert.profile_id,
            profile_name=alert.profile.name if alert.profile else "Unknown",
            role=alert.profile.role.value if alert.profile else "unknown",
            confidence=alert.detection.confidence if alert.detection else 0.0,
            acknowledged=alert.acknowledged,
            snapshot_tone=tones[i % len(tones)],
        ))
    
    return results


# ==================== WebSocket Endpoints ====================

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time alerts."""
    await manager.connect("alerts", websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Alert channel message: {data}")
    except WebSocketDisconnect:
        await manager.disconnect("alerts", websocket)


@app.websocket("/ws/cameras")
async def websocket_cameras(websocket: WebSocket):
    """WebSocket endpoint for camera health updates."""
    await manager.connect("cameras", websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Camera channel message: {data}")
    except WebSocketDisconnect:
        await manager.disconnect("cameras", websocket)


@app.websocket("/ws/kpis")
async def websocket_kpis(websocket: WebSocket):
    """WebSocket endpoint for real-time KPIs."""
    await manager.connect("kpis", websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"KPI channel message: {data}")
    except WebSocketDisconnect:
        await manager.disconnect("kpis", websocket)


# ==================== Thresholds Endpoints ====================

@app.get("/api/thresholds", response_model=ModelThresholdsResponse)
def get_thresholds(db: Session = Depends(get_db)):
    """Get current model thresholds."""
    # Defaults
    thresholds = {
        "similarity_confidence": 0.60,
        "liveness_threshold": 0.50,
        "age_variance": 5.0,
    }
    
    # Load from DB if available
    db_thresholds = db.query(ModelThreshold).all()
    for t in db_thresholds:
        if t.name in thresholds:
            thresholds[t.name] = t.value
    
    return ModelThresholdsResponse(**thresholds)


@app.post("/api/thresholds", response_model=ModelThresholdsResponse)
def update_thresholds(
    thresholds: ModelThresholdsResponse,
    db: Session = Depends(get_db)
):
    """Update model thresholds."""
    for field, value in thresholds.dict().items():
        existing = db.query(ModelThreshold).filter(ModelThreshold.name == field).first()
        if existing:
            existing.value = value
        else:
            db.add(ModelThreshold(id=field, name=field, value=value))
    
    db.commit()
    
    # Broadcast to all connected clients
    import asyncio
    asyncio.create_task(
        manager.broadcast("kpis", {"thresholds": thresholds.dict()})
    )
    
    return thresholds


if __name__ == "__main__":
    import uvicorn
    if settings.debug:
        uvicorn.run(
            "main:app",
            host=settings.host,
            port=settings.port,
            reload=True,
        )
    else:
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            reload=False,
        )
