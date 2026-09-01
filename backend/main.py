"""FastAPI application entry point."""
import logging
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, date
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query, Request, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, text, case, select

import io
import cv2
import numpy as np

import sys
import os
import asyncio
import threading
import yaml
from pathlib import Path

# Add parent directory to sys.path to access facial_recognition module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from facial_recognition.detector import InsightFaceDetector
    from facial_recognition.recognizer import Recognizer
    from facial_recognition.logger import DetectionLogger
    from facial_recognition.pending import PendingSaver
except ImportError as e:
    InsightFaceDetector = None
    Recognizer = None
    DetectionLogger = None
    PendingSaver = None
    logging.getLogger(__name__).warning(f"Could not import facial_recognition modules: {e}")

# ---------- streaming imports ----------
from starlette.responses import StreamingResponse

from config import settings
from database import Base, engine, get_db
from models import (
    Camera, Profile, Detection, Alert, ModelThreshold, Embedding, CameraTransition,
    DetectionStatus as DetectionStatusEnum, CameraStatus as CameraStatusEnum,
    ProfileRole as ProfileRoleEnum, Gender as GenderEnum, EmbeddingStatus as EmbeddingStatusEnum
)
from schemas import (
    CameraResponse, ProfileResponse, DetectionResponse, FaceLogResponse,
    AlertResponse, SystemKpisResponse, ModelThresholdsResponse,
    ForensicMatchResponse, AttendanceRecordResponse,
    DuplicateCandidateResponse, TrajectoryNodeResponse, SubjectTrajectoryResponse,
    MovementEdgeResponse, MovementNetworkResponse,
    FootfallBucketResponse, DemographicSliceResponse, SystemKpisFullResponse,
    ForensicMatchFullResponse, AttendanceRecordFullResponse,
    ForensicMatchFullResponse, AttendanceRecordFullResponse,
    AlertAcknowledgeRequest, ProfileMergeRequest, ProfileCreateRequest,
    DetectionCreateRequest, ForensicVectorSearchRequest
)
from websocket import manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global state for AI models and camera pipelines
ai_models = {}
# camera_id -> CameraPipeline  (populated in lifespan when not on Render)
camera_pipelines: dict = {}

# ---------- frame relay store ------------------------------------------------
# camera_id -> latest raw JPEG bytes pushed by the edge node.
# Written by the push WebSocket, read by the MJPEG streaming endpoint.
# asyncio.Event per camera_id notifies waiting MJPEG consumers when a new
# frame arrives so they don't busy-poll.

import dataclasses

@dataclasses.dataclass
class _FrameSlot:
    jpeg: bytes = b""
    event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)

# Populated lazily; access only from the event-loop thread.
_frame_store: dict[str, _FrameSlot] = {}

def _get_slot(camera_id: str) -> "_FrameSlot":
    if camera_id not in _frame_store:
        _frame_store[camera_id] = _FrameSlot()
    return _frame_store[camera_id]
# -----------------------------------------------------------------------------


def _load_recognition_config() -> dict:
    """Load facial_recognition/config.yaml relative to the repo root."""
    root = Path(__file__).resolve().parent.parent
    cfg_path = root / "facial_recognition" / "config.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _start_camera_pipelines(detector, recognizer, det_logger) -> dict:
    """Instantiate and start one CameraPipeline per configured camera source."""
    try:
        from facial_recognition.main import CameraPipeline, build_camera_sources
        from facial_recognition.pending import PendingSaver as _PS
    except ImportError as exc:
        logger.warning("Cannot start camera pipelines: %s", exc)
        return {}

    cfg = _load_recognition_config()
    cam_w = int(cfg.get("camera_width", 640))
    cam_h = int(cfg.get("camera_height", 480))
    det_w = int(cfg.get("inference_frame_width", 320))
    det_h = int(cfg.get("inference_frame_height", 320))
    reconnect = int(cfg.get("reconnect_interval_seconds", 10))

    root = Path(__file__).resolve().parent.parent / "facial_recognition"
    pending_saver = _PS(root / "pending")

    pipelines = {}
    for camera_id, source in build_camera_sources(cfg):
        try:
            pipeline = CameraPipeline(
                camera_id=camera_id,
                source=source,
                detector=detector,
                recognizer=recognizer,
                logger=det_logger,
                frame_size=(det_w, det_h),
                pending_saver=pending_saver,
                capture_width=cam_w,
                capture_height=cam_h,
                reconnect_interval=reconnect,
                model_name="buffalo_s",
            )
            pipeline.start()
            pipelines[camera_id] = pipeline
            logger.info("Started CameraPipeline: %s (source=%s)", camera_id, source)
        except Exception as exc:
            logger.error("Failed to start pipeline %s: %s", camera_id, exc)
    return pipelines

AVATAR_TONES = ['sky', 'amber', 'rose', 'violet', 'emerald', 'cyan', 'orange', 'indigo']


def snapshot_tone_for(key: str) -> str:
    return AVATAR_TONES[hash(key) % len(AVATAR_TONES)]


def is_pending_unknown_identity(identity: str) -> bool:
    if not identity or identity == "Unknown":
        return True
    if identity.startswith("Person "):
        parts = identity.split()
        if len(parts) == 2 and parts[1].isdigit():
            return True
    return False


def parse_gender(value: Optional[str]) -> GenderEnum:
    if not value:
        return GenderEnum.unknown
    normalized = value.lower()
    if normalized == GenderEnum.male.value:
        return GenderEnum.male
    if normalized == GenderEnum.female.value:
        return GenderEnum.female
    return GenderEnum.unknown


def resolve_detection_identity(db: Session, identity: str):
    """Return (profile, profile_id, status) for an edge identity string."""
    if is_pending_unknown_identity(identity):
        return None, None, DetectionStatusEnum.unknown

    profile = db.query(Profile).filter(Profile.name == identity).first()
    if profile:
        if profile.role in (ProfileRoleEnum.blacklist, ProfileRoleEnum.watchlist):
            status = DetectionStatusEnum.flagged
        else:
            status = DetectionStatusEnum.recognized
        return profile, profile.id, status

    new_id = str(uuid.uuid4())
    profile = Profile(id=new_id, name=identity, role=ProfileRoleEnum.visitor)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile, new_id, DetectionStatusEnum.recognized


def alert_meta_for_detection(
    status: DetectionStatusEnum,
    profile: Optional[Profile],
    identity: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    if status == DetectionStatusEnum.unknown:
        label = identity if identity != "Unknown" else "unknown subject"
        return True, "medium", f"Unknown face detected ({label})"
    if profile and profile.role == ProfileRoleEnum.blacklist:
        return True, "critical", f"Blacklist match: {profile.name}"
    if profile and profile.role == ProfileRoleEnum.watchlist:
        return True, "high", f"Watchlist match: {profile.name}"
    if status == DetectionStatusEnum.flagged:
        name = profile.name if profile else identity
        return True, "high", f"Flagged identity: {name}"
    return False, None, None


def build_face_log_payload(
    detection: Detection,
    camera: Camera,
    profile: Optional[Profile],
) -> dict:
    return {
        "id": detection.id,
        "camera_id": detection.camera_id,
        "camera_name": camera.name,
        "timestamp": detection.timestamp.isoformat() + "Z",
        "status": detection.status.value,
        "confidence": detection.confidence,
        "liveness_score": detection.liveness_score,
        "profile_id": detection.profile_id,
        "profile_name": profile.name if profile else None,
        "role": profile.role.value if profile else None,
        "age": detection.age or 0,
        "gender": detection.gender.value if detection.gender else "unknown",
        "wearing_mask": detection.wearing_mask,
        "wearing_glasses": detection.wearing_glasses,
        "snapshot_tone": snapshot_tone_for(detection.id),
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    # Startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")
    
    should_load_ai = (
        InsightFaceDetector is not None
        and (settings.enable_forensic_search or settings.enable_edge_pipelines)
    )

    if should_load_ai:
        logger.info("Loading AI Models via facial_recognition module...")
        try:
            detector = InsightFaceDetector(use_gpu=False, det_size=(320, 320), fast_detector=False, model_name='buffalo_s')
            ai_models['detector'] = detector
            logger.info("AI Models Loaded")

            # Embedded camera pipelines are opt-in; the normal local workflow
            # runs the edge process separately from the API.
            if settings.enable_edge_pipelines and Recognizer is not None and DetectionLogger is not None:
                try:
                    cfg = _load_recognition_config()
                    root = Path(__file__).resolve().parent.parent / "facial_recognition"
                    gallery_path = str(root / cfg.get("gallery_path", "known_faces/gallery.npz"))
                    log_path = str(root / cfg.get("log_file", "detections.csv"))
                    database_url = os.environ.get("DATABASE_URL", cfg.get("database_url"))
                    recognizer = Recognizer(gallery_path=gallery_path, threshold=float(cfg.get("similarity_threshold", 0.35)))
                    det_logger = DetectionLogger(log_path=log_path, db_url=database_url)
                    ai_models["recognizer"] = recognizer
                    ai_models["det_logger"] = det_logger
                    started = _start_camera_pipelines(detector, recognizer, det_logger)
                    camera_pipelines.update(started)
                    logger.info("Camera pipelines started: %s", list(camera_pipelines.keys()))
                except Exception as exc:
                    logger.warning("Camera pipelines could not start: %s", exc)
        except Exception as e:
            logger.warning(f"Failed to load AI models: {e}")
    else:
        logger.warning(
            "AI logic is disabled (module missing, running on Render without "
            "ENABLE_FORENSIC_SEARCH=true, or model load skipped)."
        )
        
    yield
    # Shutdown
    logger.info("Shutting down")
    for pipeline in camera_pipelines.values():
        try:
            pipeline.stop()
        except Exception:
            pass
    camera_pipelines.clear()
    det_logger_obj = ai_models.get("det_logger")
    if det_logger_obj:
        try:
            det_logger_obj.close()
        except Exception:
            pass
    ai_models.clear()

async def extract_face_embedding(file: UploadFile) -> Optional[np.ndarray]:
    """Helper to extract face embedding from uploaded file."""
    detector = ai_models.get('detector')
    if not detector:
        return None
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        
        # Get faces using the facial_recognition module
        results = detector.detect(img)
        if not results:
            return None
            
        # Return largest face embedding (bbox is [x0, y0, x1, y1])
        faces = sorted(results, key=lambda f: (f['bbox'][2]-f['bbox'][0]) * (f['bbox'][3]-f['bbox'][1]), reverse=True)
        face = faces[0]
        embedding = detector.extract_embedding(img, face)
        return embedding
    except Exception as e:
        logger.error(f"Error extracting embedding: {e}")
        return None


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

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)


def verify_edge_node(x_api_key: str = Header(..., alias="X-API-Key")):
    expected_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key


@app.post("/api/internal/notify_update")
async def notify_update(api_key: str = Depends(verify_edge_node)):
    """Endpoint for detection pipeline to notify about new detections."""
    import asyncio
    asyncio.create_task(manager.broadcast("kpis", {"refresh": True}))
    asyncio.create_task(manager.broadcast("alerts", {"refresh": True}))
    return {"status": "ok"}


@app.get("/api/internal/gallery")
def get_gallery(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """Get active gallery embeddings for edge nodes."""
    profiles = db.query(Profile).filter(Profile.embedding_count > 0).all()
    labels = []
    embeddings = []
    for profile in profiles:
        for emb in profile.embeddings:
            labels.append(profile.name)
            embeddings.append(emb.vector)
    return {"labels": labels, "embeddings": embeddings}


@app.post("/api/detections", response_model=DetectionResponse)
async def create_detection(
    req: DetectionCreateRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """Endpoint for edge node to push detection logs."""
    import asyncio
    
    camera = db.query(Camera).filter(Camera.id == req.camera_id).first()
    if not camera:
        camera = Camera(id=req.camera_id, name=req.camera_id, status=CameraStatusEnum.online)
        db.add(camera)
        db.commit()
        db.refresh(camera)
        
    profile_id = None
    profile = None
    profile, profile_id, status = resolve_detection_identity(db, req.identity)

    if profile_id:
        previous = db.query(Detection).filter(
            Detection.profile_id == profile_id,
            Detection.timestamp < req.timestamp,
        ).order_by(Detection.timestamp.desc()).first()
        if previous and previous.camera_id != req.camera_id:
            previous_timestamp = previous.timestamp
            if previous_timestamp.tzinfo is None and req.timestamp.tzinfo is not None:
                previous_timestamp = previous_timestamp.replace(tzinfo=req.timestamp.tzinfo)
            elif previous_timestamp.tzinfo is not None and req.timestamp.tzinfo is None:
                previous_timestamp = previous_timestamp.replace(tzinfo=None)
            travel_seconds = (req.timestamp - previous_timestamp).total_seconds()
            config = _load_recognition_config()
            routes = config.get("camera_routes", {}) or {}
            allowed_targets = routes.get(previous.camera_id)
            max_travel = int(config.get("max_camera_travel_seconds", 300))
            route_allowed = allowed_targets is None or req.camera_id in allowed_targets
            if 0 < travel_seconds <= max_travel and route_allowed:
                db.add(CameraTransition(
                    id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    from_camera_id=previous.camera_id,
                    to_camera_id=req.camera_id,
                    detected_at=req.timestamp,
                    travel_seconds=travel_seconds,
                    confidence=req.confidence,
                ))

    if profile is not None:
        profile.last_seen = req.timestamp

    detection = Detection(
        id=str(uuid.uuid4()),
        camera_id=req.camera_id,
        profile_id=profile_id,
        timestamp=req.timestamp,
        status=status,
        confidence=req.confidence,
        bbox=f"[{int(req.bbox[0])}, {int(req.bbox[1])}, {int(req.bbox[2])}, {int(req.bbox[3])}]",
        liveness_score=0.0,
        age=req.age,
        gender=parse_gender(req.gender),
        wearing_mask=False,
        wearing_glasses=False,
    )
    db.add(detection)
    db.commit()
    db.refresh(detection)

    should_alert, severity, reason = alert_meta_for_detection(status, profile, req.identity)
    if should_alert and severity and reason:
        alert = Alert(
            id=str(uuid.uuid4()),
            detection_id=detection.id,
            camera_id=req.camera_id,
            profile_id=profile_id,
            timestamp=req.timestamp,
            severity=severity,
            reason=reason,
            acknowledged=False,
        )
        db.add(alert)
        db.commit()

    face_log = build_face_log_payload(detection, camera, profile)

    # Broadcast face log directly (frontend expects detection fields at message.data)
    asyncio.create_task(manager.broadcast("alerts", face_log))
    asyncio.create_task(manager.broadcast("kpis", {"refresh": True}))

    return DetectionResponse.from_orm(detection)


@app.get("/api/analytics/movement-network", response_model=MovementNetworkResponse)
def get_movement_network(hours: int = Query(24), db: Session = Depends(get_db)):
    """Return observed identified-person movement between cameras."""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    rows = db.query(
        CameraTransition.from_camera_id,
        CameraTransition.to_camera_id,
        func.count(CameraTransition.id).label("count"),
        func.max(CameraTransition.detected_at).label("last_seen"),
        func.avg(CameraTransition.travel_seconds).label("average_travel_seconds"),
    ).filter(
        CameraTransition.detected_at >= start_time,
    ).group_by(
        CameraTransition.from_camera_id,
        CameraTransition.to_camera_id,
    ).order_by(func.max(CameraTransition.detected_at).desc()).all()

    camera_ids = {row.from_camera_id for row in rows} | {row.to_camera_id for row in rows}
    cameras = {camera.id: camera for camera in db.query(Camera).filter(Camera.id.in_(camera_ids)).all()}
    return MovementNetworkResponse(edges=[MovementEdgeResponse(
        fromCameraId=row.from_camera_id,
        fromCameraName=cameras.get(row.from_camera_id).name if cameras.get(row.from_camera_id) else row.from_camera_id,
        toCameraId=row.to_camera_id,
        toCameraName=cameras.get(row.to_camera_id).name if cameras.get(row.to_camera_id) else row.to_camera_id,
        count=int(row.count),
        lastSeen=row.last_seen,
        averageTravelSeconds=round(float(row.average_travel_seconds), 1),
    ) for row in rows])


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


@app.post("/api/profiles", response_model=ProfileResponse)
async def create_profile(
    name: str = Form(...),
    role: Optional[str] = Form("visitor"),
    department: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    gender: Optional[str] = Form("unknown"),
    notes: Optional[str] = Form(None),
    photos: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Enroll a new profile and extract face embeddings."""
    new_id = str(uuid.uuid4())
    profile = Profile(
        id=new_id,
        name=name,
        role=ProfileRoleEnum(role),
        department=department,
        embedding_status=EmbeddingStatusEnum.pending,
        embedding_count=0,
        enrolled_at=datetime.utcnow()
    )
    db.add(profile)
    db.commit()

    if photos:
        for photo in photos:
            embedding = await extract_face_embedding(photo)
            if embedding is not None:
                emb_id = str(uuid.uuid4())
                # embedding is a 512-dim numpy array
                db_emb = Embedding(
                    id=emb_id,
                    profile_id=new_id,
                    vector=embedding.tolist()
                )
                db.add(db_emb)
                profile.embedding_count += 1
        
        if profile.embedding_count > 0:
            profile.embedding_status = EmbeddingStatusEnum.indexed
            db.commit()
            
    db.refresh(profile)
    return ProfileResponse.from_orm(profile)


@app.post("/api/profiles/merge")
def merge_profiles(
    req: ProfileMergeRequest,
    db: Session = Depends(get_db)
):
    """Merge two profiles."""
    keep_id = req.keepProfile or req.keepProfileId or req.profileAId
    delete_id = req.profileBId if keep_id == req.profileAId else req.profileAId
    
    keep_profile = db.query(Profile).filter(Profile.id == keep_id).first()
    delete_profile = db.query(Profile).filter(Profile.id == delete_id).first()
    
    if not keep_profile or not delete_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    # Re-assign foreign keys
    db.query(Detection).filter(Detection.profile_id == delete_id).update({"profile_id": keep_id})
    db.query(Embedding).filter(Embedding.profile_id == delete_id).update({"profile_id": keep_id})
    db.query(Alert).filter(Alert.profile_id == delete_id).update({"profile_id": keep_id})
    
    # Update embedding count
    keep_profile.embedding_count += delete_profile.embedding_count
    
    db.delete(delete_profile)
    db.commit()
    
    return {
        "merged": True,
        "keptProfileId": keep_id,
        "deletedProfileId": delete_id
    }


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
            snapshot_tone=snapshot_tone_for(det.id),
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
            snapshot_tone=snapshot_tone_for(alert.id),
        ))
    
    return results


@app.post("/api/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: str,
    req: AlertAcknowledgeRequest,
    db: Session = Depends(get_db)
):
    """Acknowledge an alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.acknowledged = req.acknowledged
    db.commit()
    
    return AlertResponse(
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
        snapshot_tone="sky",
    )


# ==================== Video Streaming Endpoints ====================

async def _mjpeg_frame_generator(camera_id: str):
    """
    Async generator that yields MJPEG boundary chunks for a given camera.

    Priority:
      1. Frame store — JPEG bytes pushed by the remote edge node via
         /ws/video/push/{camera_id}.  This is the path used on Render.
      2. Local CameraPipeline — when the backend is running locally with
         the pipeline in-process (non-Render dev mode).
      3. Black placeholder — keeps the <img> alive when nothing is streaming.
    """
    BOUNDARY = b"--frame"
    BLANK = cv2.imencode(
        ".jpg",
        np.zeros((240, 320, 3), dtype=np.uint8),
        [cv2.IMWRITE_JPEG_QUALITY, 50],
    )[1].tobytes()

    while True:
        # --- 1. Remote push via frame store (Render / cloud) ---
        slot = _get_slot(camera_id)
        if slot.jpeg:
            jpeg_bytes = slot.jpeg
            slot.event.clear()
            yield (
                BOUNDARY
                + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg_bytes)).encode()
                + b"\r\n\r\n"
                + jpeg_bytes
                + b"\r\n"
            )
            # Wait up to 200 ms for the next pushed frame before looping
            try:
                await asyncio.wait_for(slot.event.wait(), timeout=0.2)
            except asyncio.TimeoutError:
                pass
            continue

        # --- 2. Local in-process pipeline (dev / local mode) ---
        pipeline = camera_pipelines.get(camera_id)
        frame = pipeline.get_frame() if pipeline is not None else None
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            jpeg_bytes = buf.tobytes() if ok else BLANK
        else:
            # --- 3. Placeholder ---
            jpeg_bytes = BLANK
            await asyncio.sleep(0.5)  # slow down when idle

        yield (
            BOUNDARY
            + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
            + str(len(jpeg_bytes)).encode()
            + b"\r\n\r\n"
            + jpeg_bytes
            + b"\r\n"
        )
        if frame is not None:
            await asyncio.sleep(1.0 / 25)  # ~25 fps cap


@app.get(
    "/api/cameras/{camera_id}/stream",
    summary="MJPEG live stream for an annotated camera feed",
    responses={200: {"content": {"multipart/x-mixed-replace; boundary=frame": {}}}},
)
async def stream_camera(camera_id: str):
    """
    Returns a continuous MJPEG stream for the requested camera.

    Works for any camera_id registered in the running pipeline (e.g. 'webcam',
    'rtsp-1').  When the backend is running on Render or the pipeline has not
    started, a black placeholder frame is streamed instead.
    """
    return StreamingResponse(
        _mjpeg_frame_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            # Prevent browsers / proxies from buffering the stream
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/cameras/{camera_id}/stream/snapshot")
async def stream_snapshot(camera_id: str):
    """Return a single JPEG snapshot of the latest annotated frame."""
    # Prefer frame store (cloud/Render), fall back to local pipeline
    slot = _get_slot(camera_id)
    if slot.jpeg:
        return StreamingResponse(
            iter([slot.jpeg]),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )
    pipeline = camera_pipelines.get(camera_id)
    frame = pipeline.get_frame() if pipeline is not None else None
    if frame is None:
        blank = np.zeros((240, 320, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", blank, [cv2.IMWRITE_JPEG_QUALITY, 70])
    else:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(status_code=500, detail="Frame encoding failed")
    return StreamingResponse(
        iter([buf.tobytes()]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


# ==================== Edge Video Push ====================

@app.post("/api/internal/cameras/{camera_id}/frame", status_code=204)
async def push_camera_frame(
    camera_id: str,
    request: Request,
    api_key: str = Depends(verify_edge_node),
):
    """Accept the latest annotated JPEG from an edge camera over HTTPS.

    This avoids relying on a long-lived inbound WebSocket connection at the
    deployment proxy. Only the most recent frame is retained in memory.
    """
    jpeg = await request.body()
    if not jpeg or len(jpeg) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Invalid frame size")

    slot = _get_slot(camera_id)
    slot.jpeg = jpeg
    slot.event.set()
    return Response(status_code=204)


# Legacy WebSocket receiver kept for local deployments.

@app.websocket("/ws/video/push/{camera_id}")
async def video_push(camera_id: str, websocket: WebSocket):
    """
    WebSocket endpoint for the local edge node to push annotated JPEG frames
    to the cloud backend.

    Protocol (binary messages):
      - Edge sends raw JPEG bytes each frame.
      - Server stores the latest bytes in the frame store so MJPEG consumers
        can serve them immediately.

    Authentication:
      - The edge node must include the API key as a query parameter:
        wss://your-backend/ws/video/push/webcam?api_key=<EDGE_API_KEY>
    """
    expected_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
    api_key = websocket.query_params.get("api_key", "")
    if api_key != expected_key:
        await websocket.close(code=4003, reason="Invalid API key")
        return

    await websocket.accept()
    slot = _get_slot(camera_id)
    logger.info("Edge node connected for camera '%s'", camera_id)
    try:
        while True:
            data = await websocket.receive_bytes()
            if not data:
                continue
            slot.jpeg = data
            slot.event.set()   # wake any waiting MJPEG consumers
    except WebSocketDisconnect:
        logger.info("Edge node disconnected for camera '%s'", camera_id)
    except Exception as exc:
        logger.warning("video_push error for '%s': %s", camera_id, exc)


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


# ==================== Analytics & Forensic ====================

def run_forensic_vector_query(
    db: Session,
    target_embedding: List[float],
    threshold: float = 0.60,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    camera_ids: Optional[List[str]] = None,
    gender: Optional[str] = None,
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    wearing_mask: Optional[bool] = None,
    wearing_glasses: Optional[bool] = None,
) -> list[ForensicMatchResponse]:
    """Search enrolled gallery embeddings and annotate matches from detection history."""
    if len(target_embedding) != 512:
        raise HTTPException(status_code=422, detail="Probe embedding must contain 512 values.")

    max_distance = 1.0 - threshold
    camera_filter = [camera_id.strip() for camera_id in (camera_ids or []) if camera_id.strip()]

    detection_filters = []
    if date_from is not None:
        detection_filters.append(Detection.timestamp >= date_from)
    if date_to is not None:
        detection_filters.append(Detection.timestamp <= date_to)
    if camera_filter:
        detection_filters.append(Detection.camera_id.in_(camera_filter))
    if gender and gender.lower() != "all":
        detection_filters.append(Detection.gender == parse_gender(gender))
    if age_min is not None:
        detection_filters.append(Detection.age >= age_min)
    if age_max is not None:
        detection_filters.append(Detection.age <= age_max)
    if wearing_mask is True:
        detection_filters.append(Detection.wearing_mask.is_(True))
    if wearing_glasses is True:
        detection_filters.append(Detection.wearing_glasses.is_(True))

    distance_expr = Embedding.vector.cosine_distance(target_embedding)
    query = db.query(
        Profile,
        distance_expr.label("distance")
    ).join(Embedding, Profile.id == Embedding.profile_id).filter(
        distance_expr <= max_distance
    )

    if detection_filters:
        matching_profile_ids = select(Detection.profile_id).filter(
            Detection.profile_id.isnot(None),
            *detection_filters,
        ).distinct()
        query = query.filter(Profile.id.in_(matching_profile_ids))

    results = query.order_by("distance").limit(25).all()

    matches = []
    seen = set()
    for profile, distance in results:
        if profile.id in seen:
            continue
        seen.add(profile.id)
        latest_detection_query = db.query(Detection).filter(
            Detection.profile_id == profile.id
        )
        if detection_filters:
            latest_detection_query = latest_detection_query.filter(*detection_filters)
        latest_detection = latest_detection_query.order_by(
            Detection.timestamp.desc()
        ).first()
        matches.append(
            ForensicMatchResponse(
                profile_id=profile.id,
                profile_name=profile.name,
                role=profile.role.value if profile.role else None,
                match_score=1.0 - float(distance),
                embeddings_matched=profile.embedding_count,
                last_seen=(
                    latest_detection.timestamp
                    if latest_detection
                    else profile.last_seen
                ),
                camera_name=(
                    latest_detection.camera.name
                    if latest_detection and latest_detection.camera
                    else None
                ),
                avatarTone=snapshot_tone_for(profile.id),
            )
        )
        if len(matches) >= 10:
            break
    return matches


@app.post("/api/internal/forensic/search-vector", response_model=list[ForensicMatchResponse])
def run_forensic_vector_search(
    req: ForensicVectorSearchRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """Run forensic search from a probe embedding generated by an edge node."""
    return run_forensic_vector_query(
        db=db,
        target_embedding=[float(v) for v in req.embedding],
        threshold=req.threshold,
        date_from=req.date_from,
        date_to=req.date_to,
        camera_ids=req.camera_ids,
        gender=req.gender,
        age_min=req.age_min,
        age_max=req.age_max,
        wearing_mask=req.wearing_mask,
        wearing_glasses=req.wearing_glasses,
    )


@app.post("/api/forensic/search", response_model=list[ForensicMatchResponse])
async def run_forensic_search(
    image: UploadFile = File(None),
    threshold: float = Form(0.60),
    date_from: Optional[datetime] = Form(None),
    date_to: Optional[datetime] = Form(None),
    camera_ids: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    age_min: Optional[int] = Form(None),
    age_max: Optional[int] = Form(None),
    wearing_mask: Optional[bool] = Form(None),
    wearing_glasses: Optional[bool] = Form(None),
    db: Session = Depends(get_db)
):
    """Run forensic search using pgvector."""
    if not image:
        raise HTTPException(status_code=400, detail="Upload a probe image to run forensic search.")

    if not ai_models.get("detector"):
        raise HTTPException(
            status_code=503,
            detail=(
                "Forensic image search is not enabled on this backend. "
                "Run the backend locally, or set ENABLE_FORENSIC_SEARCH=true "
                "on Render and redeploy."
            ),
        )
    
    target_embedding = await extract_face_embedding(image)
    if target_embedding is None:
        raise HTTPException(
            status_code=422,
            detail="No face embedding could be extracted from the uploaded image.",
        )

    return run_forensic_vector_query(
        db=db,
        target_embedding=target_embedding.tolist(),
        threshold=threshold,
        date_from=date_from,
        date_to=date_to,
        camera_ids=[
            camera_id.strip()
            for camera_id in (camera_ids or "").split(",")
            if camera_id.strip()
        ],
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        wearing_mask=wearing_mask,
        wearing_glasses=wearing_glasses,
    )

@app.get("/api/analytics/duplicates", response_model=list[DuplicateCandidateResponse])
def get_duplicates(db: Session = Depends(get_db)):
    """Find duplicate profiles using pgvector."""
    sql = text("""
        SELECT e1.profile_id as p1_id, p1.name as p1_name, p1.role as p1_role, p1.created_at as p1_created,
               e2.profile_id as p2_id, p2.name as p2_name, p2.role as p2_role, p2.created_at as p2_created,
               1 - (e1.vector <=> e2.vector) as similarity
        FROM embeddings e1
        JOIN embeddings e2 ON e1.id < e2.id 
                           AND e1.profile_id != e2.profile_id
                           AND (e1.vector <=> e2.vector) < 0.1
        JOIN profiles p1 ON e1.profile_id = p1.id
        JOIN profiles p2 ON e2.profile_id = p2.id
        ORDER BY similarity DESC
        LIMIT 20
    """)
    result = db.execute(sql)
    
    candidates = []
    seen = set()
    for row in result:
        pair = tuple(sorted([row.p1_id, row.p2_id]))
        if pair in seen:
            continue
        seen.add(pair)
        
        candidates.append(DuplicateCandidateResponse(
            id=f"{row.p1_id}:{row.p2_id}",
            profileAId=row.p1_id,
            profileAName=row.p1_name,
            profileARole=row.p1_role.value if hasattr(row.p1_role, 'value') else str(row.p1_role),
            profileAAvatarTone=snapshot_tone_for(row.p1_id),
            profileBId=row.p2_id,
            profileBName=row.p2_name,
            profileBRole=row.p2_role.value if hasattr(row.p2_role, 'value') else str(row.p2_role),
            profileBAvatarTone=snapshot_tone_for(row.p2_id),
            cosineSimilarity=float(row.similarity),
            sharedSightings=0,
        ))
    return candidates

@app.get("/api/analytics/trajectory", response_model=SubjectTrajectoryResponse)
def get_trajectory(profileId: str = Query(...), hours: int = Query(24), db: Session = Depends(get_db)):
    start_time = datetime.utcnow() - timedelta(hours=hours)
    
    profile = db.query(Profile).filter(Profile.id == profileId).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    detections = db.query(Detection).filter(
        Detection.profile_id == profileId,
        Detection.timestamp >= start_time
    ).order_by(Detection.timestamp.asc()).all()
    
    path = []
    for d in detections:
        path.append(TrajectoryNodeResponse(
            cameraId=d.camera_id,
            cameraName=d.camera.name if d.camera else "Unknown",
            zone=d.camera.zone if d.camera else "General",
            timestamp=d.timestamp,
            confidence=d.confidence,
            snapshotTone=snapshot_tone_for(d.id),
        ))
        
    return SubjectTrajectoryResponse(
        profileId=profileId,
        profileName=profile.name,
        role=profile.role.value,
        path=path
    )

@app.get("/api/analytics/footfall", response_model=list[FootfallBucketResponse])
def get_footfall(days: int = Query(7), db: Session = Depends(get_db)):
    start_time = datetime.utcnow() - timedelta(days=days)
    
    results = db.query(
        extract('hour', Detection.timestamp).label('hour'),
        func.count(Detection.id).label('total'),
        func.sum(case((Detection.status == DetectionStatusEnum.recognized, 1), else_=0)).label('recognized'),
        func.sum(case((Detection.status == DetectionStatusEnum.unknown, 1), else_=0)).label('unknown')
    ).filter(Detection.timestamp >= start_time).group_by(extract('hour', Detection.timestamp)).all()
    
    buckets = {}
    for r in results:
        hour_str = f"{int(r.hour):02d}:00"
        buckets[hour_str] = FootfallBucketResponse(
            hour=hour_str,
            detections=r.total,
            recognized=r.recognized or 0,
            unknown=r.unknown or 0
        )
        
    final_res = []
    for i in range(24):
        hour_str = f"{i:02d}:00"
        final_res.append(buckets.get(hour_str, FootfallBucketResponse(hour=hour_str, detections=0, recognized=0, unknown=0)))
    return final_res

@app.get("/api/analytics/age-distribution", response_model=list[DemographicSliceResponse])
def get_age_distribution(db: Session = Depends(get_db)):
    results = db.query(Detection.age, func.count(Detection.id)).filter(Detection.age != None).group_by(Detection.age).all()
    
    buckets = {"18-24": 0, "25-34": 0, "35-44": 0, "45-54": 0, "55+": 0}
    for age, count in results:
        if age < 18: continue
        elif age <= 24: buckets["18-24"] += count
        elif age <= 34: buckets["25-34"] += count
        elif age <= 44: buckets["35-44"] += count
        elif age <= 54: buckets["45-54"] += count
        else: buckets["55+"] += count
        
    return [DemographicSliceResponse(label=k, value=v) for k, v in buckets.items()]

@app.get("/api/analytics/gender-distribution", response_model=list[DemographicSliceResponse])
def get_gender_distribution(db: Session = Depends(get_db)):
    results = db.query(Detection.gender, func.count(Detection.id)).group_by(Detection.gender).all()
    slices = []
    for gender, count in results:
        if gender:
            slices.append(DemographicSliceResponse(label=gender.value.capitalize(), value=count))
    return slices

@app.get("/api/analytics/attendance", response_model=list[AttendanceRecordFullResponse])
def get_attendance(days: int = Query(7), db: Session = Depends(get_db)):
    start_time = datetime.utcnow() - timedelta(days=days)
    
    results = db.query(
        Detection.profile_id,
        func.min(Detection.timestamp).label('check_in'),
        func.max(Detection.timestamp).label('check_out'),
        func.count(Detection.id).label('total_sightings'),
    ).filter(
        Detection.profile_id != None,
        Detection.timestamp >= start_time
    ).group_by(Detection.profile_id).all()

    if not results:
        return []

    records = []
    profile_ids = [r.profile_id for r in results]
    profiles = {p.id: p for p in db.query(Profile).filter(Profile.id.in_(profile_ids)).all()}
    
    for row in results:
        profile = profiles.get(row.profile_id)
        if not profile:
            continue
        records.append(AttendanceRecordFullResponse(
            profileId=profile.id,
            profileName=profile.name,
            role=profile.role.value,
            department=profile.department,
            checkIn=row.check_in,
            checkOut=row.check_out,
            totalSightings=int(row.total_sightings or 0),
            avatarTone=snapshot_tone_for(profile.id),
        ))
    return records


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
