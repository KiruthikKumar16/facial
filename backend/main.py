"""FastAPI application entry point."""
import logging
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, date, timezone
import json
import hashlib
from typing import Optional, List, Dict, Any

from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect, Depends, Query, Request, UploadFile, File, Form, HTTPException, Header
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
from database import Base, engine, ensure_detection_event_id_column, get_db
from models import (
    Camera, CameraConfig, Profile, Detection, Alert, ModelThreshold, Embedding, CameraTransition, SequenceAcknowledgment, EventProvenance, UnregisteredSubject,
    DetectionStatus as DetectionStatusEnum, CameraStatus as CameraStatusEnum,
    ProfileRole as ProfileRoleEnum, Gender as GenderEnum, EmbeddingStatus as EmbeddingStatusEnum
)
from schemas import (
    CameraResponse, ProfileResponse, ProfileUpdateRequest, DetectionResponse, ProfileCreateRequest, ProfileMergeRequest,
    UnregisteredSubjectResponse, UnregisteredSubjectRenameRequest, UnregisteredSubjectRegisterRequest,
    UnregisteredSubjectAssignRequest, UnregisteredSubjectMergeRequest,
    FaceLogResponse, AlertResponse,
    CameraConfigResponse, CameraConfigUpdateRequest, CameraConfigRollbackRequest, CameraConfigHistoryResponse,
    SyncReconciliationRequest,
    SyncReconciliationResponse,
    CameraSyncRanges,
    SystemKpisResponse, ModelThresholdsResponse,
    ForensicMatchResponse, ForensicVectorSearchRequest, AttendanceRecordResponse,
    DuplicateCandidateResponse, TrajectoryNodeResponse, SubjectTrajectoryResponse,
    MovementEdgeResponse, MovementNetworkResponse,
    FootfallBucketResponse, DemographicSliceResponse, SystemKpisFullResponse,
    ForensicMatchFullResponse, AttendanceRecordFullResponse,
    DetectionCreateRequest,
    DetectionBatchRequest, SequenceSyncInfo,
    CameraEdgeCreateRequest, CameraEdgeResponse, CameraNodeResponse, CameraTopologyResponse,
    CrossCameraEvaluationRequest, CrossCameraEvaluationResponse,
    VectorSearchRequest, VectorSearchResponse, VectorSearchMatch, GalleryResponse,
    VersionBundleResponse,
    NodeHealthReportRequest, NodeHealthReportResponse,
    ProvenanceResponse, ProvenanceStageResponse, ProvenanceCandidateResponse,
    ProvenanceRetentionRequest, ProvenanceRetentionResponse, AlertAcknowledgeRequest,
)
from websocket import manager

from facial_recognition.topology import CameraTopologyGraph, CameraEdge
from facial_recognition.cross_camera_tracker import CrossCameraContinuityTracker, TransitionType
from facial_recognition.version_bundle import ModelConfigVersionBundle, EmbeddingVersionValidator, IncompatibleEmbeddingModelError

# Initialize global topology graph and cross-camera tracker
topology_graph = CameraTopologyGraph()
continuity_tracker = CrossCameraContinuityTracker(topology_graph=topology_graph)
active_version_bundle = ModelConfigVersionBundle()

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
    ensure_detection_event_id_column()
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
    """Get active gallery embeddings with versioning for edge nodes."""
    profiles = db.query(Profile).filter(Profile.embedding_count > 0).all()
    labels = []
    embeddings = []
    profile_ids = []
    for profile in profiles:
        for emb in profile.embeddings:
            labels.append(profile.name)
            embeddings.append(np.asarray(emb.vector, dtype=np.float32).reshape(-1).tolist())
            profile_ids.append(profile.id)

    # Compute a deterministic gallery version hash/count
    gallery_version = len(profiles) * 100 + len(labels)
    if gallery_version == 0:
        gallery_version = 1

    return {
        "version": gallery_version,
        "labels": labels,
        "embeddings": embeddings,
        "profile_ids": profile_ids,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/internal/vector-search", response_model=VectorSearchResponse)
def cloud_vector_search(
    req: VectorSearchRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """
    Hierarchical cloud vector search against enrolled gallery profiles.
    Strictly validates AI embedding model compatibility before vector comparison
    to prevent silent false matches from comparing vectors in different metric spaces.
    """
    t0 = time.perf_counter()
    query_vec = np.array(req.embedding, dtype=np.float32).flatten()
    q_norm = np.linalg.norm(query_vec)

    # Validate model compatibility against known models
    query_model = req.embedding_model_version or "w600k_mbf_v1"
    if query_model not in EmbeddingVersionValidator.KNOWN_MODEL_DIMENSIONS and not EmbeddingVersionValidator.COMPATIBILITY_GROUPS.get(query_model):
        raise HTTPException(
            status_code=400,
            detail=f"Unrecognized or unsupported embedding model version '{query_model}'.",
        )

    matches = []
    if q_norm >= 1e-6:
        # Load all enrolled profiles and embeddings
        profiles = db.query(Profile).filter(Profile.embedding_count > 0).all()
        candidates = []
        for p in profiles:
            for emb in p.embeddings:
                if emb.vector:
                    target_vec = np.array(emb.vector, dtype=np.float32).flatten()
                    emb_model = getattr(emb, 'model_version', 'w600k_mbf_v1') or 'w600k_mbf_v1'
                    
                    # Strictly check compatibility
                    if not EmbeddingVersionValidator.are_compatible(query_model, emb_model, len(query_vec), len(target_vec)):
                        continue  # Skip incompatible embeddings during migration

                    t_norm = np.linalg.norm(target_vec)
                    if t_norm >= 1e-6:
                        sim = float(np.dot(query_vec, target_vec) / (q_norm * t_norm))
                        if sim >= req.threshold:
                            candidates.append((p.name, sim, p.id, emb_model))

        # Sort by similarity descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = candidates[:req.top_k]
        for name, score, p_id, emb_model in top_candidates:
            matches.append(VectorSearchMatch(
                identity=name,
                score=score,
                profile_id=p_id,
                model_version=emb_model,
            ))

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return VectorSearchResponse(
        matches=matches,
        search_latency_ms=latency_ms,
        queried_model_version=query_model,
    )


@app.post("/api/detections", response_model=DetectionResponse)
async def create_detection(
    req: DetectionCreateRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """
    Endpoint for edge node to push detection logs.
    
    Idempotency: If event_id is provided, uses it as an idempotency key.
    Retransmitting the same detection with the same event_id returns existing record.
    """
    import asyncio
    
    sync_info = None
    is_duplicate = False
    is_out_of_order = False
    is_gap_detected = False
    ack_to_update = None

    if req.device_id and req.sequence_number is not None:
        ack = db.query(SequenceAcknowledgment).filter(
            SequenceAcknowledgment.device_id == req.device_id,
            SequenceAcknowledgment.camera_id == req.camera_id
        ).first()
        
        if not ack:
            ack = SequenceAcknowledgment(
                id=str(uuid.uuid4()),
                device_id=req.device_id,
                camera_id=req.camera_id,
                last_acknowledged_sequence=0
            )
            db.add(ack)
            db.flush()
            
        dup_check = db.query(Detection).filter(
            Detection.device_id == req.device_id,
            Detection.camera_id == req.camera_id,
            Detection.sequence_number == req.sequence_number
        ).first()
        
        if dup_check:
            is_duplicate = True
        elif req.sequence_number <= ack.last_acknowledged_sequence:
            is_out_of_order = True
        elif req.sequence_number > ack.last_acknowledged_sequence + 1:
            is_gap_detected = True
            
        if not is_duplicate and req.sequence_number > ack.last_acknowledged_sequence:
            ack.last_acknowledged_sequence = req.sequence_number
            ack_to_update = ack
            
        sync_info = SequenceSyncInfo(
            device_id=req.device_id,
            camera_id=req.camera_id,
            last_acknowledged_sequence=ack.last_acknowledged_sequence,
            is_duplicate=is_duplicate,
            is_out_of_order=is_out_of_order,
            is_gap_detected=is_gap_detected
        )

    # Removed python-level memory check to prevent race condition.
    # Duplicates are now handled atomically at the database level via IntegrityError.

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
            
            # Cross-Camera continuity evaluation with topology and temporal constraints
            classification, reasoning = continuity_tracker.evaluate_transition(
                from_camera_id=previous.camera_id,
                to_camera_id=req.camera_id,
                elapsed_seconds=max(0.001, travel_seconds),
                embedding_similarity=req.confidence,
            )
            
            db.add(CameraTransition(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                from_camera_id=previous.camera_id,
                to_camera_id=req.camera_id,
                detected_at=req.timestamp,
                travel_seconds=travel_seconds,
                confidence=req.confidence,
                transition_type=classification.value,
                similarity=req.confidence,
                temporal_score=reasoning.temporal_score,
                reasoning_metadata=json.dumps(reasoning.to_dict()),
            ))

    if profile is not None:
        profile.last_seen = req.timestamp

    detection = Detection(
        id=str(uuid.uuid4()),
        event_id=req.event_id,  # Required Idempotency key
        embedding_vector=req.embedding,
        device_id=req.device_id,
        sequence_number=req.sequence_number,
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
        priority=req.priority.value if hasattr(req.priority, 'value') else req.priority,
        config_version=req.camera_config_version or req.config_version or 1,
        detection_model_version=req.detection_model_version or "scrfd_500m_bnkps_v1",
        embedding_model_version=req.embedding_model_version or "w600k_mbf_v1",
        gallery_version=req.gallery_version or 1,
        threshold_version=req.threshold_version or 1,
        camera_config_version=req.camera_config_version or req.config_version or 1,
        algorithm_version=req.algorithm_version or "temporal_fusion_v2",
        version_bundle_hash=req.version_bundle_hash or ModelConfigVersionBundle(
            detection_model_version=req.detection_model_version or "scrfd_500m_bnkps_v1",
            embedding_model_version=req.embedding_model_version or "w600k_mbf_v1",
            gallery_version=req.gallery_version or 1,
            threshold_version=req.threshold_version or 1,
            camera_config_version=req.camera_config_version or req.config_version or 1,
            algorithm_version=req.algorithm_version or "temporal_fusion_v2",
        ).bundle_hash,
    )
    
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(detection)
        db.flush()
        if ack_to_update is not None:
            ack_to_update.last_synced_event_id = req.event_id
        db.commit()
        db.refresh(detection)
        inserted = True

        # Store Provenance Lineage Record
        prov_dict = req.provenance or {}
        frame_ref = prov_dict.get("frame_reference", f"frm_{req.camera_id}_{int(req.timestamp.timestamp()*1000)}")
        track_id = prov_dict.get("track_id")
        obs_refs = json.dumps(prov_dict.get("observation_references", [f"obs_{frame_ref}_01"]))
        cand_matches = json.dumps(prov_dict.get("candidate_matches", [{"identity": req.identity or "Unknown", "score": req.confidence, "rank": 1}]))
        emb_fp = prov_dict.get("embedding_fingerprint", hashlib.sha256(f"emb_{req.event_id}".encode()).hexdigest())
        dec_tier = prov_dict.get("decision_tier", "LOCAL_HIGH_CONFIDENCE")
        chain_hash = prov_dict.get("provenance_chain_hash", hashlib.sha256(f"chain_{req.event_id}".encode()).hexdigest())

        prov_record = EventProvenance(
            id=str(uuid.uuid4()),
            event_id=req.event_id,
            camera_id=req.camera_id,
            frame_reference=frame_ref,
            track_id=track_id,
            observation_references=obs_refs,
            detection_model_version=req.detection_model_version or "scrfd_500m_bnkps_v1",
            embedding_model_version=req.embedding_model_version or "w600k_mbf_v1",
            embedding_fingerprint=emb_fp,
            candidate_matches=cand_matches,
            decision_tier=dec_tier,
            selected_identity=req.identity or "Unknown",
            confidence=req.confidence,
            decision_timestamp=req.timestamp,
            sync_event_id=prov_dict.get("sync_event_id", f"sync_{req.event_id}"),
            provenance_chain_hash=chain_hash,
        )
        db.add(prov_record)
        db.commit()
    except IntegrityError:
        db.rollback()
        # The event_id already exists. This handles concurrent duplicate submissions safely.
        existing = db.query(Detection).filter(Detection.event_id == req.event_id).first()
        if not existing:
            raise  # IntegrityError wasn't caused by event_id uniqueness
        
        logger.info(f"Detection {req.event_id} already exists (idempotent retry)")
        resp = DetectionResponse.from_orm(existing)
        resp.sync_info = sync_info
        resp.inserted = False
        return resp

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

    resp = DetectionResponse.from_orm(detection)
    resp.sync_info = sync_info
    resp.inserted = inserted
    return resp


@app.post("/api/detections/batch", response_model=List[DetectionResponse])
async def create_detections_batch(
    reqs: DetectionBatchRequest,
    db: Session = Depends(get_db),
    edge_id: str = Depends(verify_edge_node)
):
    """
    Ingest a batch of detections efficiently.
    """
    responses = []
    for req in reqs.detections:
        try:
            resp = await create_detection(req, db, edge_id)
            responses.append(resp)
        except Exception as e:
            logger.error(f"Failed to process event in batch {req.event_id}: {e}")
            # If one fails, we can just skip it or handle it. 
            # In a real batch we might return partial success or 207 Multi-Status.
            # But here we'll just ignore failed ones from the response to let edge retry them?
            # Actually edge retries everything not returned? Edge expects 200 OK.
            pass
            
    return responses


@app.post("/api/detections/reconcile", response_model=SyncReconciliationResponse)
def reconcile_sync(
    req: SyncReconciliationRequest,
    db: Session = Depends(get_db),
    edge_id: str = Depends(verify_edge_node)
):
    """
    Reconcile edge sync state with the cloud.
    Finds exact missing sequence ranges.
    """
    reconciled_cameras = []
    
    for cam_meta in req.cameras:
        # Check if backend has SequenceAcknowledgment
        ack = db.query(SequenceAcknowledgment).filter(
            SequenceAcknowledgment.device_id == req.device_id,
            SequenceAcknowledgment.camera_id == cam_meta.camera_id
        ).first()
        
        last_ack = ack.last_acknowledged_sequence if ack else 0
        
        # Determine the start of the window we need to check
        # We start from the earliest known 'completed' state, or 1
        edge_completed = cam_meta.last_completed_sequence or 0
        start_search = min(last_ack, edge_completed)
        if start_search == 0:
            start_search = 1
            
        end_search = cam_meta.highest_local_sequence
        
        if end_search < start_search:
            reconciled_cameras.append(CameraSyncRanges(camera_id=cam_meta.camera_id, missing_ranges=[]))
            continue
            
        # Get present sequences in the range
        present_seqs = db.query(Detection.sequence_number).filter(
            Detection.device_id == req.device_id,
            Detection.camera_id == cam_meta.camera_id,
            Detection.sequence_number >= start_search,
            Detection.sequence_number <= end_search
        ).order_by(Detection.sequence_number.asc()).all()
        
        present_set = {seq[0] for seq in present_seqs if seq[0] is not None}
        
        # Find missing ranges
        missing_ranges = []
        current_range_start = None
        
        for seq in range(start_search, end_search + 1):
            if seq not in present_set:
                if current_range_start is None:
                    current_range_start = seq
            else:
                if current_range_start is not None:
                    missing_ranges.append((current_range_start, seq - 1))
                    current_range_start = None
                    
        if current_range_start is not None:
            missing_ranges.append((current_range_start, end_search))
            
        reconciled_cameras.append(CameraSyncRanges(
            camera_id=cam_meta.camera_id,
            missing_ranges=missing_ranges
        ))
        
    return SyncReconciliationResponse(reconciled_cameras=reconciled_cameras)


@app.get("/api/analytics/movement-network", response_model=MovementNetworkResponse)
def get_movement_network(hours: int = Query(24), db: Session = Depends(get_db)):
    """Return observed identified-person movement between cameras."""
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
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
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ==================== KPI Endpoints ====================

@app.get("/api/kpis", response_model=SystemKpisResponse)
def get_kpis(db: Session = Depends(get_db)):
    """Get system KPIs."""
    today = datetime.now(timezone.utc).date()
    
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


# ==================== Camera Configuration Endpoints ====================

@app.get("/api/cameras/{camera_id}/config", response_model=CameraConfigResponse)
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
            created_at=datetime.now(timezone.utc)
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    return CameraConfigResponse.from_orm(config)


@app.post("/api/cameras/{camera_id}/config", response_model=CameraConfigResponse)
@app.put("/api/cameras/{camera_id}/config", response_model=CameraConfigResponse)
def update_camera_config(
    camera_id: str,
    req: CameraConfigUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new version of recognition configuration for a camera.
    Deactivates older versions and activates the new version.
    """
    import json
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
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    logger.info(f"Camera {camera_id} configuration updated to version {next_version}")
    return CameraConfigResponse.from_orm(new_config)


@app.post("/api/cameras/{camera_id}/config/rollback/{version}", response_model=CameraConfigResponse)
def rollback_camera_config_path(
    camera_id: str,
    version: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return _execute_rollback(camera_id, version, notes, db)


@app.post("/api/cameras/{camera_id}/config/rollback", response_model=CameraConfigResponse)
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
        created_at=datetime.now(timezone.utc)
    )
    db.add(rollback_config)
    db.commit()
    db.refresh(rollback_config)

    logger.info(f"Camera {camera_id} rolled back to parameters of v{version} as new v{next_version}")
    return CameraConfigResponse.from_orm(rollback_config)


@app.get("/api/cameras/{camera_id}/config/history", response_model=CameraConfigHistoryResponse)
def get_camera_config_history(camera_id: str, db: Session = Depends(get_db)):
    """Get full configuration audit history for a camera."""
    configs = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera_id
    ).order_by(CameraConfig.version.desc()).all()

    active = next((c.version for c in configs if c.is_active), 1)

    return CameraConfigHistoryResponse(
        camera_id=camera_id,
        active_version=active,
        history=[CameraConfigResponse.from_orm(c) for c in configs]
    )


@app.get("/api/internal/camera_configs", response_model=List[CameraConfigResponse])
def get_all_active_camera_configs(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """Bulk sync endpoint for edge nodes to fetch active configurations for all cameras."""
    configs = db.query(CameraConfig).filter(CameraConfig.is_active == True).all()
    return [CameraConfigResponse.from_orm(c) for c in configs]


# ==================== Camera Topology & Cross-Camera Continuity Endpoints ====================

@app.get("/api/topology", response_model=CameraTopologyResponse)
def get_camera_topology(db: Session = Depends(get_db)):
    """Get active camera topology graph with allowed transition edges."""
    # Synchronize registered cameras as topology nodes
    cameras = db.query(Camera).all()
    for cam in cameras:
        if cam.id not in topology_graph.nodes:
            topology_graph.add_node(
                camera_id=cam.id,
                name=cam.name or cam.id,
                zone=cam.zone or "",
            )
    return topology_graph.to_dict()


@app.post("/api/topology/edges", response_model=CameraEdgeResponse)
def add_topology_edge(
    edge_req: CameraEdgeCreateRequest,
    db: Session = Depends(get_db)
):
    """Add or update an allowed physical transition edge between two cameras."""
    edge = topology_graph.add_edge(
        from_camera_id=edge_req.from_camera_id,
        to_camera_id=edge_req.to_camera_id,
        min_travel_seconds=edge_req.min_travel_seconds,
        max_travel_seconds=edge_req.max_travel_seconds,
        typical_travel_seconds=edge_req.typical_travel_seconds,
        distance_meters=edge_req.distance_meters,
        transition_probability=edge_req.transition_probability,
        bidirectional=edge_req.bidirectional,
    )
    return {
        "from_camera_id": edge.from_camera_id,
        "to_camera_id": edge.to_camera_id,
        "min_travel_seconds": edge.min_travel_seconds,
        "max_travel_seconds": edge.max_travel_seconds,
        "typical_travel_seconds": edge.typical_travel_seconds,
        "distance_meters": edge.distance_meters,
        "transition_probability": edge.transition_probability,
        "bidirectional": edge.bidirectional,
    }


@app.post("/api/tracking/cross-camera-evaluate", response_model=CrossCameraEvaluationResponse)
def evaluate_cross_camera_transition(
    req: CrossCameraEvaluationRequest,
    db: Session = Depends(get_db)
):
    """
    Evaluate cross-camera identity continuity using topology and temporal constraints.
    Returns reasoning metadata and classification (CONFIRMED, PROBABLE, UNCERTAIN).
    """
    classification, reasoning = continuity_tracker.evaluate_transition(
        from_camera_id=req.from_camera_id,
        to_camera_id=req.to_camera_id,
        elapsed_seconds=req.elapsed_seconds,
        embedding_similarity=req.embedding_similarity,
    )
    return reasoning.to_dict()


# ==================== System Version Bundle Endpoint ====================

@app.get("/api/system/version-bundle", response_model=VersionBundleResponse)
def get_system_version_bundle():
    """
    Get current immutable version snapshot for detection model, embedding model,
    gallery, thresholds, camera configuration, and algorithm versions.
    """
    return active_version_bundle.to_dict()


# ==================== Edge Node Health & Adaptive Controller Endpoints ====================

node_health_store: Dict[str, Dict[str, Any]] = {}

@app.post("/api/nodes/health", response_model=NodeHealthReportResponse)
def report_node_health(
    req: NodeHealthReportRequest,
    api_key: str = Depends(verify_edge_node)
):
    """
    Ingest live health metrics, operational mode, and adaptive runtime decisions
    from an edge recognition node.
    """
    now = datetime.now(timezone.utc)
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


@app.get("/api/nodes/health")
def get_all_nodes_health(
    db: Session = Depends(get_db)
):
    """Get latest health snapshots and runtime modes for all active edge nodes."""
    return {"nodes": list(node_health_store.values())}


# ==================== Recognition Provenance Endpoints ====================

@app.get("/api/detections/{event_id}/provenance", response_model=ProvenanceResponse)
def get_detection_provenance(
    event_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve full 7-stage recognition lineage graph and audit provenance for an event.
    (Camera -> Frame -> Track -> Embedding Fingerprint -> Candidates -> Decision -> Cloud Sync)
    """
    det = None
    prov = db.query(EventProvenance).filter(EventProvenance.event_id == event_id).first()
    if not prov:
        # The dashboard may provide either the detection UUID or event_id.
        det = db.query(Detection).filter(Detection.event_id == event_id).first()
        if not det:
            det = db.query(Detection).filter(Detection.id == event_id).first()
        if det:
            prov = db.query(EventProvenance).filter(EventProvenance.event_id == det.event_id).first()

    if not prov:
        # Check if detection exists to synthesize default provenance if legacy
        if not det:
            det = db.query(Detection).filter(Detection.event_id == event_id).first()
        if not det:
            raise HTTPException(status_code=404, detail="Recognition event provenance not found")
        
        # Synthesize fallback provenance
        frame_ref = f"frm_{det.camera_id}_{int(det.timestamp.timestamp()*1000)}"
        emb_fp = hashlib.sha256(f"emb_{det.event_id}".encode()).hexdigest()
        candidates = [{"identity": det.identity or "Unknown", "score": det.confidence or 0.0, "rank": 1}]
        obs_refs = [f"obs_{frame_ref}_01"]
        chain_hash = hashlib.sha256(f"chain_{det.event_id}".encode()).hexdigest()
        
        stages = [
            ProvenanceStageResponse(stage_name="1. Camera Ingestion", stage_id=f"cam_{det.camera_id}", timestamp=det.timestamp.timestamp(), metadata={"camera_id": det.camera_id}),
            ProvenanceStageResponse(stage_name="2. Frame Acquisition", stage_id=frame_ref, timestamp=det.timestamp.timestamp(), metadata={"frame_reference": frame_ref}),
            ProvenanceStageResponse(stage_name="3. Face Tracking", stage_id="track_untracked", timestamp=det.timestamp.timestamp(), metadata={"track_id": None}),
            ProvenanceStageResponse(stage_name="4. Embedding Extraction", stage_id=f"emb_{emb_fp[:12]}", timestamp=det.timestamp.timestamp(), metadata={"embedding_fingerprint": emb_fp}),
            ProvenanceStageResponse(stage_name="5. Candidate Evaluation", stage_id=f"eval_{det.event_id}", timestamp=det.timestamp.timestamp(), metadata={"candidates": candidates}),
            ProvenanceStageResponse(stage_name="6. Recognition Decision", stage_id=f"dec_{det.event_id}", timestamp=det.timestamp.timestamp(), metadata={"selected_identity": det.identity, "confidence": det.confidence}),
            ProvenanceStageResponse(stage_name="7. Cloud Synchronization", stage_id=f"sync_{det.event_id}", timestamp=det.timestamp.timestamp(), metadata={"cloud_detection_id": det.id}),
        ]
        
        return ProvenanceResponse(
            event_id=det.event_id,
            detection_id=det.id,
            camera_id=det.camera_id,
            camera_config_version=det.camera_config_version or det.config_version or 1,
            frame_reference=frame_ref,
            track_id=None,
            observation_references=obs_refs,
            detection_model_version=det.detection_model_version or "scrfd_500m_bnkps_v1",
            embedding_model_version=det.embedding_model_version or "w600k_mbf_v1",
            embedding_fingerprint=emb_fp,
            candidate_matches=[ProvenanceCandidateResponse(**c) for c in candidates],
            decision_tier="LOCAL_HIGH_CONFIDENCE",
            selected_identity=det.identity or "Unknown",
            confidence=det.confidence or 0.0,
            decision_timestamp=det.timestamp,
            sync_event_id=f"sync_{det.event_id}",
            cloud_record_id=det.id,
            provenance_chain_hash=chain_hash,
            stages=stages,
        )

    # Parse stored JSON fields
    obs_list = json.loads(prov.observation_references) if prov.observation_references else []
    cand_list = json.loads(prov.candidate_matches) if prov.candidate_matches else []
    det = db.query(Detection).filter(Detection.event_id == prov.event_id).first()
    
    stages = [
        ProvenanceStageResponse(stage_name="1. Camera Ingestion", stage_id=f"cam_{prov.camera_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"camera_id": prov.camera_id}),
        ProvenanceStageResponse(stage_name="2. Frame Acquisition", stage_id=prov.frame_reference, timestamp=prov.decision_timestamp.timestamp(), metadata={"frame_reference": prov.frame_reference, "obs_count": len(obs_list)}),
        ProvenanceStageResponse(stage_name="3. Face Tracking", stage_id=prov.track_id or "untracked", timestamp=prov.decision_timestamp.timestamp(), metadata={"track_id": prov.track_id, "observations": obs_list}),
        ProvenanceStageResponse(stage_name="4. Embedding Extraction", stage_id=f"emb_{prov.embedding_fingerprint[:12]}", timestamp=prov.decision_timestamp.timestamp(), metadata={"embedding_fingerprint": prov.embedding_fingerprint, "model": prov.embedding_model_version}),
        ProvenanceStageResponse(stage_name="5. Candidate Evaluation", stage_id=f"eval_{prov.event_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"candidates": cand_list}),
        ProvenanceStageResponse(stage_name="6. Recognition Decision", stage_id=f"dec_{prov.event_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"selected_identity": prov.selected_identity, "confidence": prov.confidence, "tier": prov.decision_tier}),
        ProvenanceStageResponse(stage_name="7. Cloud Synchronization", stage_id=prov.sync_event_id or f"sync_{prov.event_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"chain_hash": prov.provenance_chain_hash}),
    ]

    return ProvenanceResponse(
        event_id=prov.event_id,
        detection_id=det.id if det else None,
        camera_id=prov.camera_id,
        camera_config_version=(det.camera_config_version or det.config_version or 1) if det else 1,
        frame_reference=prov.frame_reference,
        track_id=prov.track_id,
        observation_references=obs_list,
        detection_model_version=prov.detection_model_version,
        embedding_model_version=prov.embedding_model_version,
        embedding_fingerprint=prov.embedding_fingerprint,
        candidate_matches=[ProvenanceCandidateResponse(**c) for c in cand_list],
        decision_tier=prov.decision_tier,
        selected_identity=prov.selected_identity,
        confidence=prov.confidence,
        decision_timestamp=prov.decision_timestamp,
        sync_event_id=prov.sync_event_id,
        cloud_record_id=det.id if det else None,
        provenance_chain_hash=prov.provenance_chain_hash,
        stages=stages,
    )


@app.post("/api/provenance/retention", response_model=ProvenanceRetentionResponse)
def enforce_provenance_retention(
    req: ProvenanceRetentionRequest,
    db: Session = Depends(get_db),
):
    """
    Enforce data retention policy on intermediate provenance records.
    Purges historical processing lineage older than max_retention_days while retaining the detection.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=req.max_retention_days)
    
    # Count & delete expired records
    expired_records = db.query(EventProvenance).filter(EventProvenance.created_at < cutoff).all()
    count = len(expired_records)
    for r in expired_records:
        db.delete(r)
    db.commit()
    
    remaining_count = db.query(EventProvenance).count()
    return ProvenanceRetentionResponse(
        purged_records_count=count,
        retained_records_count=remaining_count,
        cutoff_timestamp=cutoff,
    )


# ==================== Profile Endpoints ====================

def _subject_vector(value: Any) -> Optional[np.ndarray]:
    if value is None:
        return None
    try:
        vector = np.asarray(value, dtype=np.float32).reshape(-1)
        if vector.size != 512 or not np.isfinite(vector).all():
            return None
        norm = np.linalg.norm(vector)
        return vector / norm if norm else None
    except (TypeError, ValueError):
        return None


def _refresh_unregistered_subjects(db: Session, threshold: Optional[float] = None) -> None:
    threshold = threshold if threshold is not None else settings.unregistered_similarity_threshold
    subjects = db.query(UnregisteredSubject).filter(UnregisteredSubject.status == "active").all()
    pending = db.query(Detection).filter(
        Detection.profile_id.is_(None),
        Detection.status == DetectionStatusEnum.unknown,
        Detection.embedding_vector.is_not(None),
        Detection.unregistered_subject_id.is_(None),
    ).order_by(Detection.timestamp.asc()).all()

    for detection in pending:
        vector = _subject_vector(detection.embedding_vector)
        if vector is None:
            continue
        best_subject = None
        best_similarity = -1.0
        for subject in subjects:
            representative = _subject_vector(subject.representative_embedding)
            if representative is None:
                continue
            similarity = float(np.dot(vector, representative))
            if similarity > best_similarity:
                best_subject, best_similarity = subject, similarity

        if best_subject is None or best_similarity < threshold:
            subject = UnregisteredSubject(
                id=str(uuid.uuid4()),
                display_name=f"Unknown Person {len(subjects) + 1}",
                representative_embedding=vector.tolist(),
                similarity_threshold=threshold,
                status="active",
            )
            db.add(subject)
            db.flush()
            subjects.append(subject)
            best_subject = subject
        detection.unregistered_subject_id = best_subject.id

    if pending:
        db.commit()


def _subject_response(subject: UnregisteredSubject, db: Session) -> UnregisteredSubjectResponse:
    detections = db.query(Detection).filter(
        Detection.unregistered_subject_id == subject.id,
        Detection.profile_id.is_(None),
    ).order_by(Detection.timestamp.asc()).all()
    if not detections:
        raise HTTPException(status_code=404, detail="Unregistered subject not found")
    event_ids = [d.event_id or d.id for d in detections]
    fingerprint = hashlib.sha256(json.dumps(subject.representative_embedding).encode()).hexdigest()
    return UnregisteredSubjectResponse(
        id=subject.id,
        display_name=subject.display_name,
        capture_count=len(detections),
        first_seen=detections[0].timestamp,
        last_seen=detections[-1].timestamp,
        cameras=sorted({d.camera_id for d in detections}),
        best_confidence=max(float(d.confidence or 0) for d in detections),
        representative_fingerprint=fingerprint,
        vector_dimension=512,
        event_ids=event_ids[:100],
        status=subject.status,
    )


@app.get("/api/unregistered-subjects", response_model=List[UnregisteredSubjectResponse])
def get_unregistered_subjects(
    threshold: Optional[float] = Query(None, ge=0.5, le=0.99),
    db: Session = Depends(get_db),
):
    _refresh_unregistered_subjects(db, threshold)
    subjects = db.query(UnregisteredSubject).filter(UnregisteredSubject.status == "active").all()
    return [_subject_response(subject, db) for subject in subjects if db.query(Detection).filter(
        Detection.unregistered_subject_id == subject.id, Detection.profile_id.is_(None)
    ).first()]


@app.patch("/api/unregistered-subjects/{subject_id}", response_model=UnregisteredSubjectResponse)
def rename_unregistered_subject(subject_id: str, req: UnregisteredSubjectRenameRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    if not subject or not req.display_name.strip():
        raise HTTPException(status_code=404 if not subject else 422, detail="Invalid unregistered subject name" if subject else "Unregistered subject not found")
    subject.display_name = req.display_name.strip()
    db.commit()
    return _subject_response(subject, db)


@app.post("/api/unregistered-subjects/{subject_id}/register", response_model=ProfileResponse)
def register_unregistered_subject(subject_id: str, req: UnregisteredSubjectRegisterRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    if not subject:
        raise HTTPException(status_code=404, detail="Unregistered subject not found")
    try:
        role = ProfileRoleEnum(req.role)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid profile role")
    profile = Profile(id=str(uuid.uuid4()), name=req.name.strip(), role=role, department=req.department, embedding_status=EmbeddingStatusEnum.indexed, embedding_count=1, enrolled_at=datetime.now(timezone.utc))
    if not profile.name:
        raise HTTPException(status_code=422, detail="Profile name cannot be empty")
    db.add(profile)
    db.add(Embedding(id=str(uuid.uuid4()), profile_id=profile.id, vector=subject.representative_embedding))
    db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).update({"profile_id": profile.id, "status": DetectionStatusEnum.recognized, "unregistered_subject_id": None})
    subject.status = "registered"
    db.commit()
    db.refresh(profile)
    return ProfileResponse.from_orm(profile)


@app.post("/api/unregistered-subjects/{subject_id}/assign", response_model=ProfileResponse)
def assign_unregistered_subject(subject_id: str, req: UnregisteredSubjectAssignRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    profile = db.query(Profile).filter(Profile.id == req.profile_id).first()
    if not subject or not profile:
        raise HTTPException(status_code=404, detail="Unregistered subject or profile not found")
    db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).update({"profile_id": profile.id, "status": DetectionStatusEnum.recognized, "unregistered_subject_id": None})
    subject.status = "assigned"
    db.commit()
    return ProfileResponse.from_orm(profile)


@app.post("/api/unregistered-subjects/{subject_id}/merge", response_model=UnregisteredSubjectResponse)
def merge_unregistered_subject(subject_id: str, req: UnregisteredSubjectMergeRequest, db: Session = Depends(get_db)):
    target = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    source = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == req.source_subject_id, UnregisteredSubject.status == "active").first()
    if not target or not source or target.id == source.id:
        raise HTTPException(status_code=404, detail="Unregistered subject not found")
    db.query(Detection).filter(Detection.unregistered_subject_id == source.id).update({"unregistered_subject_id": target.id})
    source.status = "merged"
    db.commit()
    return _subject_response(target, db)


@app.delete("/api/unregistered-subjects/{subject_id}/events/{event_id}")
def delete_unregistered_event(subject_id: str, event_id: str, db: Session = Depends(get_db)):
    detection = db.query(Detection).filter(
        Detection.unregistered_subject_id == subject_id,
        (Detection.event_id == event_id) | (Detection.id == event_id),
    ).first()
    if not detection:
        raise HTTPException(status_code=404, detail="Unregistered event not found")
    db.query(Alert).filter(Alert.detection_id == detection.id).update({"detection_id": None})
    db.delete(detection)
    db.commit()
    return {"deleted": True, "event_id": event_id}


@app.delete("/api/unregistered-subjects/{subject_id}")
def delete_unregistered_subject(subject_id: str, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    if not subject:
        raise HTTPException(status_code=404, detail="Unregistered subject not found")
    detection_ids = [d.id for d in db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).all()]
    if detection_ids:
        db.query(Alert).filter(Alert.detection_id.in_(detection_ids)).update({"detection_id": None}, synchronize_session=False)
    db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).delete(synchronize_session=False)
    db.delete(subject)
    db.commit()
    return {"deleted": True, "subject_id": subject_id}

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
        enrolled_at=datetime.now(timezone.utc)
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


@app.put("/api/profiles/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: str, req: ProfileUpdateRequest, db: Session = Depends(get_db)):
    """Update editable profile metadata without changing stored embeddings."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if req.name is not None:
        if not req.name.strip():
            raise HTTPException(status_code=422, detail="Profile name cannot be empty")
        profile.name = req.name.strip()
    if req.role is not None:
        try:
            profile.role = ProfileRoleEnum(req.role)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid profile role")
    if req.department is not None:
        profile.department = req.department.strip() or None
    db.commit()
    db.refresh(profile)
    return ProfileResponse.from_orm(profile)


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    """Delete a profile and its vectors while retaining historical detections."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.query(Detection).filter(Detection.profile_id == profile_id).update({"profile_id": None})
    db.query(Alert).filter(Alert.profile_id == profile_id).update({"profile_id": None})
    db.query(CameraTransition).filter(CameraTransition.profile_id == profile_id).delete(synchronize_session=False)
    db.query(Embedding).filter(Embedding.profile_id == profile_id).delete(synchronize_session=False)
    db.delete(profile)
    db.commit()
    return {"deleted": True, "profile_id": profile_id}


@app.delete("/api/profiles/{profile_id}/embeddings/{embedding_id}")
def delete_profile_embedding(profile_id: str, embedding_id: str, db: Session = Depends(get_db)):
    """Delete one stored vector and keep the profile count/status consistent."""
    embedding = db.query(Embedding).filter(
        Embedding.id == embedding_id,
        Embedding.profile_id == profile_id,
    ).first()
    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    db.delete(embedding)
    if profile:
        profile.embedding_count = max(0, profile.embedding_count - 1)
        if profile.embedding_count == 0:
            profile.embedding_status = EmbeddingStatusEnum.missing
    db.commit()
    return {"deleted": True, "embedding_id": embedding_id, "profile_id": profile_id}


@app.delete("/api/profiles/{profile_id}/embeddings")
def delete_profile_embeddings(profile_id: str, db: Session = Depends(get_db)):
    """Remove all vectors for a profile without deleting the profile."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    deleted_count = db.query(Embedding).filter(Embedding.profile_id == profile_id).delete(synchronize_session=False)
    profile.embedding_count = 0
    profile.embedding_status = EmbeddingStatusEnum.missing
    db.commit()
    return {"deleted": True, "profile_id": profile_id, "deleted_count": deleted_count}


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
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    
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
    start_time = datetime.now(timezone.utc) - timedelta(days=days)
    
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
    start_time = datetime.now(timezone.utc) - timedelta(days=days)
    
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
