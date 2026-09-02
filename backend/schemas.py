"""Pydantic models for API request/response validation."""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
from pydantic import BaseModel, field_validator


# ==================== Enums ====================

class DetectionStatus(str, Enum):
    recognized = "recognized"
    flagged = "flagged"
    unknown = "unknown"


class ProfileRole(str, Enum):
    employee = "employee"
    vip = "vip"
    visitor = "visitor"
    blacklist = "blacklist"
    watchlist = "watchlist"


class EmbeddingStatus(str, Enum):
    indexed = "indexed"
    pending = "pending"
    stale = "stale"
    missing = "missing"


class Gender(str, Enum):
    male = "male"
    female = "female"
    unknown = "unknown"


class EventPriority(str, Enum):
    critical = "critical"
    high = "high"
    normal = "normal"
    low = "low"


class CameraStatus(str, Enum):
    online = "online"
    degraded = "degraded"
    offline = "offline"


# ==================== Camera ====================

class CameraBase(BaseModel):
    id: str
    name: str
    zone: Optional[str] = None
    ip_address: Optional[str] = None
    rtsp_url: Optional[str] = None


class CameraResponse(CameraBase):
    status: str
    ping_ms: int
    frame_latency_ms: int
    fps: float
    gpu_load: float
    cpu_load: float
    last_heartbeat: datetime
    detections_today: int
    
    class Config:
        from_attributes = True


# ==================== Profile ====================

class ProfileBase(BaseModel):
    name: str
    role: Optional[str] = ProfileRole.visitor
    department: Optional[str] = None


class ProfileResponse(ProfileBase):
    id: str
    embedding_status: str
    embedding_count: int
    enrolled_at: datetime
    last_seen: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None


class UnregisteredSubjectResponse(BaseModel):
    id: str
    display_name: str
    capture_count: int
    first_seen: datetime
    last_seen: datetime
    cameras: List[str]
    best_confidence: float
    representative_fingerprint: str
    vector_dimension: int
    event_ids: List[str]
    status: str


class UnregisteredSubjectRenameRequest(BaseModel):
    display_name: str


class UnregisteredSubjectRegisterRequest(BaseModel):
    name: str
    role: str = "visitor"
    department: Optional[str] = None


class UnregisteredSubjectAssignRequest(BaseModel):
    profile_id: str


class UnregisteredSubjectMergeRequest(BaseModel):
    source_subject_id: str


# ==================== Detection / FaceLog ====================

class DetectionBase(BaseModel):
    camera_id: str
    profile_id: Optional[str] = None
    timestamp: datetime
    status: str = DetectionStatus.unknown
    confidence: float = 0.0
    liveness_score: float = 0.0
    age: Optional[int] = None
    gender: Optional[Gender] = Gender.unknown
    wearing_mask: Optional[bool] = False
    wearing_glasses: Optional[bool] = False
    bbox: List[int]  # [x1, y1, x2, y2]
    priority: Optional[EventPriority] = EventPriority.normal

    @field_validator('bbox', mode='before')
    @classmethod
    def parse_bbox(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except ValueError:
                return []
        return v


class DetectionCreateRequest(BaseModel):
    camera_id: str
    identity: str
    confidence: float
    bbox: List[int]
    timestamp: datetime
    age: Optional[int] = None
    gender: Optional[str] = None
    event_id: str  # Required idempotency key (deterministic SHA-256 hash from edge node)
    device_id: Optional[str] = None
    sequence_number: Optional[int] = None
    priority: Optional[EventPriority] = EventPriority.normal
    config_version: Optional[int] = 1
    
    # AI Model and Configuration Version Tracking
    detection_model_version: Optional[str] = "scrfd_500m_bnkps_v1"
    embedding_model_version: Optional[str] = "w600k_mbf_v1"
    gallery_version: Optional[int] = 1
    threshold_version: Optional[int] = 1
    camera_config_version: Optional[int] = 1
    algorithm_version: Optional[str] = "temporal_fusion_v2"
    version_bundle_hash: Optional[str] = None
    embedding: Optional[List[float]] = None
    provenance: Optional[Dict[str, Any]] = None

class DetectionBatchRequest(BaseModel):
    detections: List[DetectionCreateRequest]

class SequenceSyncInfo(BaseModel):
    device_id: str
    camera_id: str
    last_acknowledged_sequence: int
    is_duplicate: bool
    is_out_of_order: bool
    is_gap_detected: bool

class DetectionResponse(DetectionBase):
    id: str
    event_id: Optional[str] = None
    device_id: Optional[str] = None
    sequence_number: Optional[int] = None
    config_version: Optional[int] = 1
    
    detection_model_version: Optional[str] = None
    embedding_model_version: Optional[str] = None
    gallery_version: Optional[int] = None
    threshold_version: Optional[int] = None
    camera_config_version: Optional[int] = None
    algorithm_version: Optional[str] = None
    version_bundle_hash: Optional[str] = None
    
    camera: Optional[CameraResponse] = None
    profile: Optional[ProfileResponse] = None
    sync_info: Optional[SequenceSyncInfo] = None
    inserted: bool = True  # True = newly created; False = duplicate, existing row returned
    
    class Config:
        from_attributes = True


# ==================== Camera Configuration ====================

class CameraConfigBase(BaseModel):
    detection_threshold: float = 0.50
    recognition_threshold: float = 0.35
    quality_thresholds: Optional[dict] = None
    sampling_rate: int = 1
    temporal_window: float = 3.0
    notes: Optional[str] = None

    @field_validator('quality_thresholds', mode='before')
    @classmethod
    def parse_quality_thresholds(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class CameraConfigUpdateRequest(CameraConfigBase):
    pass


class CameraConfigRollbackRequest(BaseModel):
    target_version: int
    notes: Optional[str] = None


class CameraConfigResponse(CameraConfigBase):
    id: str
    camera_id: str
    version: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CameraConfigHistoryResponse(BaseModel):
    camera_id: str
    active_version: int
    history: List[CameraConfigResponse]


class FaceLogResponse(BaseModel):
    """Detailed face detection log matching frontend FaceLog type."""
    id: str
    camera_id: str
    camera_name: str
    timestamp: str
    status: str
    confidence: float
    liveness_score: float
    profile_id: Optional[str]
    profile_name: Optional[str]
    role: Optional[str]
    age: int
    gender: str
    wearing_mask: bool
    wearing_glasses: bool
    snapshot_tone: str  # Color token for avatar


# ==================== Alerts ====================

class AlertResponse(BaseModel):
    id: str
    log_id: str
    camera_id: str
    camera_name: str
    timestamp: str
    severity: str  # critical, high, medium
    reason: str
    profile_id: Optional[str]
    profile_name: str
    role: str
    confidence: float
    acknowledged: bool
    snapshot_tone: str
    
    class Config:
        from_attributes = True


# ==================== KPIs ====================

class SystemKpisResponse(BaseModel):
    """System-wide key performance indicators."""
    total_detections: int
    unique_individuals: int
    total_profiles: int
    cameras_online: int
    critical_alerts: int
    recognitions_today: int
    unknowns_today: int
    average_confidence: float


# ==================== Thresholds ====================

class ModelThreshold(BaseModel):
    name: str
    value: float
    description: Optional[str] = None


class ModelThresholdsResponse(BaseModel):
    """Configurable model thresholds for detection/recognition."""
    similarity_confidence: float
    liveness_threshold: float
    age_variance: float
    
    class Config:
        from_attributes = True


# ==================== Forensic Search ====================

class ForensicMatchResponse(BaseModel):
    """Result of forensic face search against gallery."""
    profile_id: str
    profile_name: str
    role: Optional[str] = None
    match_score: float
    embeddings_matched: int
    last_seen: Optional[datetime]
    camera_name: Optional[str] = None
    avatarTone: str = "sky"


class ForensicVectorSearchRequest(BaseModel):
    """Forensic search request with probe embedding generated by an edge node."""
    embedding: List[float]
    threshold: float = 0.60
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    camera_ids: Optional[List[str]] = None
    gender: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    wearing_mask: Optional[bool] = None
    wearing_glasses: Optional[bool] = None


# ==================== Attendance ====================

class AttendanceRecordResponse(BaseModel):
    profile_id: str
    profile_name: str
    first_seen: datetime
    last_seen: datetime
    detection_count: int
    status: str  # present, absent, late


# ==================== Duplicate Detection ====================

class DuplicateCandidateResponse(BaseModel):
    id: str
    profileAId: str
    profileAName: str
    profileARole: str
    profileAAvatarTone: str
    profileBId: str
    profileBName: str
    profileBRole: str
    profileBAvatarTone: str
    cosineSimilarity: float
    sharedSightings: int


# ==================== Trajectory ====================

class CameraSyncMetadata(BaseModel):
    camera_id: str
    highest_local_sequence: int
    lowest_pending_sequence: Optional[int] = None
    last_completed_sequence: Optional[int] = None

class SyncReconciliationRequest(BaseModel):
    device_id: str
    cameras: List[CameraSyncMetadata]

class CameraSyncRanges(BaseModel):
    camera_id: str
    missing_ranges: List[Tuple[int, int]]

class SyncReconciliationResponse(BaseModel):
    reconciled_cameras: List[CameraSyncRanges]


class TrajectoryNodeResponse(BaseModel):
    cameraId: str
    cameraName: str
    zone: Optional[str]
    timestamp: datetime
    confidence: float
    snapshotTone: str


class SubjectTrajectoryResponse(BaseModel):
    profileId: str
    profileName: str
    role: str
    path: List[TrajectoryNodeResponse]


class MovementEdgeResponse(BaseModel):
    fromCameraId: str
    fromCameraName: str
    toCameraId: str
    toCameraName: str
    count: int
    lastSeen: datetime
    averageTravelSeconds: float


# ==================== Camera Topology & Cross-Camera Continuity ====================

class CameraEdgeCreateRequest(BaseModel):
    from_camera_id: str
    to_camera_id: str
    min_travel_seconds: float = 2.0
    max_travel_seconds: float = 120.0
    typical_travel_seconds: float = 15.0
    distance_meters: float = 10.0
    transition_probability: float = 1.0
    bidirectional: bool = False


class CameraEdgeResponse(BaseModel):
    from_camera_id: str
    to_camera_id: str
    min_travel_seconds: float
    max_travel_seconds: float
    typical_travel_seconds: float
    distance_meters: float
    transition_probability: float
    bidirectional: bool


class CameraNodeResponse(BaseModel):
    camera_id: str
    name: str
    zone: Optional[str] = ""
    location_description: Optional[str] = ""
    coordinates: Optional[Tuple[float, float]] = None


class CameraTopologyResponse(BaseModel):
    nodes: Dict[str, CameraNodeResponse]
    edges: List[CameraEdgeResponse]


class CrossCameraEvaluationRequest(BaseModel):
    from_camera_id: str
    to_camera_id: str
    elapsed_seconds: float
    embedding_similarity: float


class CrossCameraEvaluationResponse(BaseModel):
    from_camera: str
    to_camera: str
    elapsed_seconds: float
    expected_travel_range: List[float]
    temporal_score: float
    embedding_similarity: float
    topology_edge_exists: bool
    is_teleportation: bool
    is_expired: bool
    classification: str
    explanation: str


# ==================== Cloud Vector Search & Gallery Versioning ====================

class VectorSearchRequest(BaseModel):
    embedding: List[float]
    top_k: int = 1
    threshold: float = 0.50
    embedding_model_version: str = "w600k_mbf_v1"


class VectorSearchMatch(BaseModel):
    identity: str
    score: float
    profile_id: str
    model_version: str = "w600k_mbf_v1"


class VectorSearchResponse(BaseModel):
    matches: List[VectorSearchMatch]
    search_latency_ms: float
    queried_model_version: str = "w600k_mbf_v1"


class VersionBundleResponse(BaseModel):
    detection_model_version: str
    embedding_model_version: str
    gallery_version: int
    threshold_version: int
    camera_config_version: int
    algorithm_version: str
    bundle_hash: str


class GalleryResponse(BaseModel):
    version: int
    labels: List[str]
    embeddings: List[List[float]]
    profile_ids: List[str]
    synced_at: datetime


# ==================== Edge Node Health & Adaptive Runtime ====================

class NodeHealthReportRequest(BaseModel):
    device_id: str
    camera_id: Optional[str] = None
    mode: str = "NORMAL"
    metrics: Dict[str, Any]
    decisions: Optional[List[Dict[str, Any]]] = None


class NodeHealthReportResponse(BaseModel):
    status: str
    recorded_at: datetime


# ==================== Recognition Provenance Lineage ====================

class ProvenanceCandidateResponse(BaseModel):
    identity: str
    score: float
    profile_id: Optional[str] = None
    rank: int = 1


class ProvenanceStageResponse(BaseModel):
    stage_name: str
    stage_id: str
    timestamp: float
    metadata: Dict[str, Any]


class ProvenanceResponse(BaseModel):
    event_id: str
    detection_id: Optional[str] = None
    camera_id: str
    camera_config_version: int = 1
    frame_reference: str
    track_id: Optional[str] = None
    observation_references: List[str]
    detection_model_version: str
    embedding_model_version: str
    embedding_fingerprint: str
    candidate_matches: List[ProvenanceCandidateResponse]
    decision_tier: str
    selected_identity: str
    confidence: float
    decision_timestamp: datetime
    sync_event_id: Optional[str] = None
    cloud_record_id: Optional[str] = None
    provenance_chain_hash: str
    stages: List[ProvenanceStageResponse]


class ProvenanceRetentionRequest(BaseModel):
    max_retention_days: int = 30


class ProvenanceRetentionResponse(BaseModel):
    purged_records_count: int
    retained_records_count: int
    cutoff_timestamp: datetime




class MovementNetworkResponse(BaseModel):
    edges: List[MovementEdgeResponse]


# ==================== Footfall ====================

class FootfallBucketResponse(BaseModel):
    hour: str
    detections: int
    recognized: int
    unknown: int


# ==================== Demographics ====================

class DemographicSliceResponse(BaseModel):
    label: str
    value: int


# ==================== System KPIs (Full frontend shape) ====================

class SystemKpisFullResponse(BaseModel):
    connectedCameras: int
    totalCameras: int
    detectionsToday: int
    activeAlerts: int
    systemHealth: str
    gpuLoad: float
    cpuLoad: float
    avgLatencyMs: float


# ==================== Forensic Match (Full frontend shape) ====================

class ForensicMatchFullResponse(BaseModel):
    profileId: str
    profileName: str
    role: str
    cosineSimilarity: float
    lastSeen: Optional[datetime]
    cameraName: Optional[str]
    avatarTone: str


# ==================== Attendance (Full frontend shape) ====================

class AttendanceRecordFullResponse(BaseModel):
    profileId: str
    profileName: str
    role: str
    department: Optional[str]
    checkIn: Optional[datetime]
    checkOut: Optional[datetime]
    totalSightings: int
    avatarTone: str


# ==================== Alert Acknowledge ====================

class AlertAcknowledgeRequest(BaseModel):
    acknowledged: bool = True


# ==================== Profile Merge ====================

class ProfileMergeRequest(BaseModel):
    profileAId: str
    profileBId: str
    keepProfile: Optional[str] = None
    keepProfileId: Optional[str] = None
    deleteMerged: Optional[bool] = True


# ==================== Profile Create ====================

class ProfileCreateRequest(BaseModel):
    name: str
    role: Optional[str] = "visitor"
    department: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = "unknown"
    notes: Optional[str] = None
