"""Pydantic models for API request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ==================== Enums ====================

class DetectionStatus(str):
    recognized = "recognized"
    flagged = "flagged"
    unknown = "unknown"


class ProfileRole(str):
    employee = "employee"
    vip = "vip"
    visitor = "visitor"
    blacklist = "blacklist"
    watchlist = "watchlist"


class EmbeddingStatus(str):
    indexed = "indexed"
    pending = "pending"
    stale = "stale"
    missing = "missing"


class Gender(str):
    male = "male"
    female = "female"
    unknown = "unknown"


class CameraStatus(str):
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


# ==================== Detection / FaceLog ====================

class DetectionBase(BaseModel):
    camera_id: str
    profile_id: Optional[str] = None
    timestamp: datetime
    status: str = DetectionStatus.unknown
    confidence: float = 0.0
    liveness_score: float = 0.0
    age: Optional[int] = None
    gender: str = Gender.unknown
    wearing_mask: bool = False
    wearing_glasses: bool = False


class DetectionCreateRequest(BaseModel):
    camera_id: str
    identity: str
    confidence: float
    bbox: List[int]
    timestamp: datetime
    age: Optional[int] = None
    gender: Optional[str] = None


class DetectionResponse(DetectionBase):
    id: str
    camera: Optional[CameraResponse] = None
    profile: Optional[ProfileResponse] = None
    
    class Config:
        from_attributes = True


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
