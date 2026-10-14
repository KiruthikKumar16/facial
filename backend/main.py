"""FastAPI application entry point."""
import logging
import time
import uuid
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
import hashlib
from typing import Optional, List, Dict, Any

# Add parent directory to sys.path to access facial_recognition module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import IST
except ModuleNotFoundError:
    from backend.config import IST

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query, Request, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, text, case, select, or_

import hmac
from jose import jwt
from auth import SECRET_KEY, ALGORITHM

import cv2
import numpy as np

import sys
import os
import asyncio
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    if os.environ.get("SENTRY_DSN"):
        sentry_sdk.init(
            dsn=os.environ.get("SENTRY_DSN"),
            enable_tracing=True,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )
except ImportError:
    sentry_sdk = None
import yaml
from pathlib import Path

# Add parent directory to sys.path to access facial_recognition module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from facial_recognition.detector import InsightFaceDetector
    from facial_recognition.recognizer import Recognizer
    from facial_recognition.logger import DetectionLogger
    from facial_recognition.pending import PendingSaver
except Exception as e:
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
    CameraResponse, ProfileResponse, ProfileUpdateRequest, DetectionResponse, ProfileMergeRequest,
    UnregisteredSubjectResponse, UnregisteredSubjectRenameRequest, UnregisteredSubjectRegisterRequest,
    UnregisteredSubjectAssignRequest, UnregisteredSubjectMergeRequest,
    FaceLogResponse, AlertResponse,
    CameraConfigResponse, CameraConfigUpdateRequest, CameraConfigRollbackRequest, CameraConfigHistoryResponse,
    SyncReconciliationRequest,
    SyncReconciliationResponse,
    CameraSyncRanges,
    SystemKpisResponse, ModelThresholdsResponse,
    ForensicMatchResponse, ForensicVectorSearchRequest, DuplicateCandidateResponse, TrajectoryNodeResponse, SubjectTrajectoryResponse,
    MovementEdgeResponse, MovementNetworkResponse,
    FootfallBucketResponse, DemographicSliceResponse, AttendanceRecordFullResponse,
    DetectionCreateRequest,
    DetectionBatchRequest, SequenceSyncInfo,
    CameraEdgeCreateRequest, CameraEdgeResponse, CameraTopologyResponse,
    CrossCameraEvaluationRequest, CrossCameraEvaluationResponse,
    VectorSearchRequest, VectorSearchResponse, VectorSearchMatch, VersionBundleResponse,
    NodeHealthReportRequest, NodeHealthReportResponse,
    ProvenanceResponse, ProvenanceStageResponse, ProvenanceCandidateResponse,
    ProvenanceRetentionRequest, ProvenanceRetentionResponse, AlertAcknowledgeRequest,
)
from websocket import manager

from facial_recognition.topology import CameraTopologyGraph
from facial_recognition.cross_camera_tracker import CrossCameraContinuityTracker
from facial_recognition.version_bundle import ModelConfigVersionBundle, EmbeddingVersionValidator



from state import (
    ai_models, camera_pipelines, get_frame_slot, _frame_store,
    topology_graph, continuity_tracker, active_version_bundle
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
from utils import (
    snapshot_tone_for,
    is_pending_unknown_identity,
    parse_gender,
    resolve_detection_identity,
    alert_meta_for_detection,
    build_face_log_payload,
    extract_face_embedding,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    # Startup
    Base.metadata.create_all(bind=engine)
    try:
        ensure_detection_event_id_column()
    except Exception as e:
        logger.warning(f"Could not verify schema upgrade columns: {e}")
    logger.info("Database initialized")
    
    should_load_ai = (
        InsightFaceDetector is not None
        and (settings.enable_forensic_search or settings.enable_edge_pipelines)
    )

    if should_load_ai:
        logger.info("Loading AI Models via facial_recognition module...")
        try:
            use_gpu = os.environ.get("USE_GPU", "false").lower() in ("true", "1", "yes")
            if not use_gpu:
                try:
                    import torch
                    use_gpu = torch.cuda.is_available()
                except ImportError:
                    pass
            detector = InsightFaceDetector(use_gpu=use_gpu, det_size=(320, 320), fast_detector=False, model_name='buffalo_s')
            ai_models['detector'] = detector
            logger.info("AI Models Loaded (GPU: %s)", use_gpu)

            # Pre-load recognizer for remote /detect and forensic features
            if Recognizer is not None and "recognizer" not in ai_models:
                try:
                    cfg = _load_recognition_config()
                    root = Path(__file__).resolve().parent.parent / "facial_recognition"
                    gallery_path = str(root / cfg.get("gallery_path", "known_faces/gallery.npz"))
                    if os.path.exists(gallery_path):
                        ai_models["recognizer"] = Recognizer(
                            gallery_path=gallery_path,
                            threshold=float(cfg.get("similarity_threshold", 0.35))
                        )
                except Exception as ex:
                    logger.debug("Could not pre-load recognizer: %s", ex)

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
        
    from websocket import manager
    await manager.startup()
        
    yield
    # Shutdown
    logger.info("Shutting down")
    await manager.shutdown()
    for pipeline in camera_pipelines.values():
        try:
            pipeline.stop()
        except Exception:
            logger.exception("Failed to stop pipeline")
    camera_pipelines.clear()
    det_logger_obj = ai_models.get("det_logger")
    if det_logger_obj:
        try:
            det_logger_obj.close()
        except Exception:
            logger.exception("Failed to close det_logger")
    ai_models.clear()



app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

from auth import router as auth_router
app.include_router(auth_router)

from routers.system import router as system_router
app.include_router(system_router)

from routers.forensic import router as forensic_router
app.include_router(forensic_router)

from routers.unregistered import router as unregistered_router
app.include_router(unregistered_router)

from routers.logs import router as logs_router
app.include_router(logs_router)

from routers.detections import router as detections_router
app.include_router(detections_router)

from routers.analytics import router as analytics_router
app.include_router(analytics_router)

from routers.cameras import router as cameras_router
app.include_router(cameras_router)

from routers.profiles import router as profiles_router
app.include_router(profiles_router)

from routers.video_audit import router as video_audit_router
app.include_router(video_audit_router)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

from middleware import JWTMiddleware

app.add_middleware(JWTMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware with wildcard subdomain support (e.g. https://*.vercel.app, https://*.jarvislabs.run)
_exact_origins = []
_regex_patterns = []

for _origin in settings.cors_origins:
    if "*" in _origin:
        import re
        _pattern = "^" + re.escape(_origin).replace(r"\*", ".*") + "$"
        _regex_patterns.append(_pattern)
    else:
        _exact_origins.append(_origin)

_combined_origin_regex = "|".join(_regex_patterns) if _regex_patterns else None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_exact_origins,
    allow_origin_regex=_combined_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


from dependencies import verify_edge_node


@app.post("/detect")
async def detect_frame(
    file: UploadFile = File(...),
    api_key: str = Depends(verify_edge_node),
):
    """
    Remote face detection endpoint for pc_frame_sender.py and RemoteInsightFaceDetector.
    Accepts multipart/form-data frame and runs GPU/CPU detection + embedding extraction.
    """
    detector = ai_models.get("detector")
    if detector is None:
        raise HTTPException(status_code=503, detail="AI detector not loaded on this backend instance")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty frame payload")

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Failed to decode image frame")

    results = detector.detect(img)
    recognizer = ai_models.get("recognizer")

    detections = []
    for face in results:
        emb = detector.extract_embedding(img, face)
        identity = "Unknown"
        conf = float(face.get("det_score", 1.0))
        status = "unknown"

        if emb is not None and recognizer is not None:
            match_name, match_score = recognizer.recognize(emb)
            if match_name and match_score >= recognizer.threshold:
                identity = match_name
                conf = float(match_score)
                status = "recognized"

        det_data = {
            "bbox": [int(v) for v in face.get("bbox", [0, 0, 0, 0])],
            "confidence": conf,
            "identity": identity,
            "status": status,
            "gender": face.get("gender"),
            "age": face.get("age"),
        }
        if emb is not None:
            det_data["embedding"] = emb.tolist()
        detections.append(det_data)

    return {"detections": detections, "count": len(detections)}


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
        "synced_at": datetime.now(IST).isoformat(),
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
# ==================== Edge Node Health & Adaptive Controller Endpoints ====================

node_health_store: Dict[str, Dict[str, Any]] = {}

# ==================== Video Streaming Endpoints ====================

def _make_camera_placeholder(text: str = "Connecting to camera feed...") -> bytes:
    """Generate a sleek dark-slate placeholder JPEG with status text."""
    img = np.full((240, 320, 3), (28, 22, 18), dtype=np.uint8)  # dark slate BGR
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.42
    thickness = 1
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    cx = max(10, (320 - tw) // 2)
    cy = max(20, (240 + th) // 2)
    cv2.putText(img, text, (cx, cy), font, scale, (148, 163, 184), thickness, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 65])
    return buf.tobytes() if ok else b""

async def _mjpeg_frame_generator(camera_id: str):
    """
    Async generator that yields MJPEG boundary chunks for a given camera.

    Priority:
      1. Frame store — JPEG bytes pushed by the remote edge node via
         /ws/video/push/{camera_id} or POST /api/internal/cameras/{camera_id}/frame.
      2. Local CameraPipeline — when running locally with pipeline in-process.
      3. Informative placeholder — keeps the <img> alive with clear status text.
    """
    BOUNDARY = b"--frame"
    BLANK = _make_camera_placeholder(f"Camera [{camera_id}]: Offline / Waiting")

    while True:
        # --- 1. Remote push via frame store (Render / cloud) ---
        slot = get_frame_slot(camera_id)
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
    slot = get_frame_slot(camera_id)
    if slot.jpeg:
        return StreamingResponse(
            iter([slot.jpeg]),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )
    pipeline = camera_pipelines.get(camera_id)
    frame = pipeline.get_frame() if pipeline is not None else None
    if frame is None:
        jpeg_bytes = _make_camera_placeholder(f"Camera [{camera_id}]: Offline")
        return StreamingResponse(
            iter([jpeg_bytes]),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )
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

    slot = get_frame_slot(camera_id)
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
    if not (api_key and hmac.compare_digest(api_key, expected_key)):
        await websocket.close(code=4003, reason="Invalid API key")
        return

    await websocket.accept()
    slot = get_frame_slot(camera_id)
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

async def authenticate_ws(websocket: WebSocket) -> bool:
    """Validate query token (JWT) or API key before accepting WebSocket connection."""
    token = websocket.query_params.get("token")
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("sub"):
                return True
        except Exception:
            pass

    api_key = websocket.query_params.get("api_key")
    expected_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
    if api_key and hmac.compare_digest(api_key, expected_key):
        return True

    return False


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time alerts."""
    if not await authenticate_ws(websocket):
        await websocket.close(code=4001, reason="Unauthorized: invalid or missing token")
        return
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
    if not await authenticate_ws(websocket):
        await websocket.close(code=4001, reason="Unauthorized: invalid or missing token")
        return
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
    if not await authenticate_ws(websocket):
        await websocket.close(code=4001, reason="Unauthorized: invalid or missing token")
        return
    await manager.connect("kpis", websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"KPI channel message: {data}")
    except WebSocketDisconnect:
        await manager.disconnect("kpis", websocket)

