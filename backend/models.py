"""SQLAlchemy ORM models for facial recognition system."""
from datetime import datetime, timezone

def utc_now():
    return datetime.now(timezone.utc)

from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum, TypeDecorator
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
from database import Base
import enum

import json
import numpy as np

try:
    from pgvector.sqlalchemy import Vector as _PGVector

    def Vector(dim: int):
        return _PGVector(dim)
except Exception:  # pragma: no cover - local dev fallback
    class Vector(TypeDecorator):
        impl = Text
        cache_ok = True

        def __init__(self, dim: int = 512):
            self.dim = dim
            super().__init__()

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, (list, tuple, np.ndarray)):
                return json.dumps(list(value))
            return str(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return value
            return value


class CameraStatus(str, enum.Enum):
    """Camera operational status."""
    online = "online"
    degraded = "degraded"
    offline = "offline"


class DetectionStatus(str, enum.Enum):
    """Face detection classification."""
    recognized = "recognized"
    flagged = "flagged"
    unknown = "unknown"


class ProfileRole(str, enum.Enum):
    """Identity classification."""
    employee = "employee"
    vip = "vip"
    visitor = "visitor"
    blacklist = "blacklist"
    watchlist = "watchlist"


class EmbeddingStatus(str, enum.Enum):
    """Face embedding index status."""
    indexed = "indexed"
    pending = "pending"
    stale = "stale"
    missing = "missing"


class Gender(str, enum.Enum):
    """Detected gender."""
    male = "male"
    female = "female"
    unknown = "unknown"


class EventPriority(str, enum.Enum):
    """Event synchronization priority."""
    critical = "critical"
    high = "high"
    normal = "normal"
    low = "low"


class Camera(Base):
    """Camera device metadata and health."""
    __tablename__ = "cameras"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    zone = Column(String)
    ip_address = Column(String)
    rtsp_url = Column(String)
    status = Column(SQLEnum(CameraStatus), default=CameraStatus.online)
    ping_ms = Column(Integer, default=0)
    frame_latency_ms = Column(Integer, default=0)
    fps = Column(Float, default=0.0)
    gpu_load = Column(Float, default=0.0)
    cpu_load = Column(Float, default=0.0)
    last_heartbeat = Column(DateTime, default=utc_now)
    detections_today = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    detections = relationship("Detection", back_populates="camera")
    alerts = relationship("Alert", back_populates="camera")
    outgoing_transitions = relationship("CameraTransition", foreign_keys="CameraTransition.from_camera_id", back_populates="from_camera")
    incoming_transitions = relationship("CameraTransition", foreign_keys="CameraTransition.to_camera_id", back_populates="to_camera")
    configs = relationship("CameraConfig", back_populates="camera")


class Profile(Base):
    """Known identity in the gallery."""
    __tablename__ = "profiles"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    role = Column(SQLEnum(ProfileRole), default=ProfileRole.visitor)
    department = Column(String)
    embedding_status = Column(SQLEnum(EmbeddingStatus), default=EmbeddingStatus.pending)
    embedding_count = Column(Integer, default=0)
    enrolled_at = Column(DateTime, default=utc_now)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    embeddings = relationship("Embedding", back_populates="profile", cascade="all, delete-orphan")
    detections = relationship("Detection", back_populates="profile")
    alerts = relationship("Alert", back_populates="profile")


class Embedding(Base):
    """Face embedding vector (pgvector)."""
    __tablename__ = "embeddings"
    
    id = Column(String, primary_key=True, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    vector = Column(Vector(512), nullable=False)
    model_version = Column(String, nullable=False, default="w600k_mbf_v1", index=True)
    created_at = Column(DateTime, default=utc_now)
    
    # Relationships
    profile = relationship("Profile", back_populates="embeddings")


class Detection(Base):
    """Individual face detection event."""
    __tablename__ = "detections"
    
    id = Column(String, primary_key=True, index=True)
    event_id = Column(String, unique=True, nullable=True, index=True)  # Idempotency key (deterministic SHA-256)
    unregistered_subject_id = Column(String, ForeignKey("unregistered_subjects.id"), nullable=True, index=True)
    device_id = Column(String, nullable=True, index=True)
    sequence_number = Column(Integer, nullable=True, index=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    status = Column(SQLEnum(DetectionStatus), default=DetectionStatus.unknown, index=True)
    confidence = Column(Float, default=0.0)
    embedding_vector = Column(Vector(512), nullable=True)
    liveness_score = Column(Float, default=0.0)
    age = Column(Integer)
    gender = Column(SQLEnum(Gender), default=Gender.unknown)
    wearing_mask = Column(Boolean, default=False)
    wearing_glasses = Column(Boolean, default=False)
    bbox = Column(String)  # JSON serialized [x1, y1, x2, y2]
    priority = Column(SQLEnum(EventPriority), default=EventPriority.normal, index=True)
    config_version = Column(Integer, nullable=True, default=1, index=True)
    
    # AI Model and Configuration Version Tracking (Auditability & Reproducibility)
    detection_model_version = Column(String, nullable=True, default="scrfd_500m_bnkps_v1")
    embedding_model_version = Column(String, nullable=True, default="w600k_mbf_v1", index=True)
    gallery_version = Column(Integer, nullable=True, default=1)
    threshold_version = Column(Integer, nullable=True, default=1)
    camera_config_version = Column(Integer, nullable=True, default=1)
    algorithm_version = Column(String, nullable=True, default="temporal_fusion_v2")
    version_bundle_hash = Column(String, nullable=True, index=True)
    
    created_at = Column(DateTime, default=utc_now)
    
    # Relationships
    camera = relationship("Camera", back_populates="detections")
    profile = relationship("Profile", back_populates="detections")
    alert = relationship("Alert", back_populates="detection", uselist=False)
    provenance = relationship("EventProvenance", back_populates="detection", uselist=False)


class UnregisteredSubject(Base):
    """Cluster of unknown detections linked by embedding similarity."""
    __tablename__ = "unregistered_subjects"

    id = Column(String, primary_key=True, index=True)
    display_name = Column(String, nullable=False)
    representative_embedding = Column(Vector(512), nullable=False)
    similarity_threshold = Column(Float, nullable=False, default=0.35)
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    detections = relationship("Detection", backref="unregistered_subject")


class EventProvenance(Base):
    """Recognition processing stage lineage and audit provenance."""
    __tablename__ = "event_provenances"

    id = Column(String, primary_key=True, index=True)
    event_id = Column(String, ForeignKey("detections.event_id"), nullable=False, unique=True, index=True)
    camera_id = Column(String, nullable=False, index=True)
    frame_reference = Column(String, nullable=False)
    track_id = Column(String, nullable=True)
    observation_references = Column(Text, nullable=True)  # JSON list
    detection_model_version = Column(String, nullable=False)
    embedding_model_version = Column(String, nullable=False)
    embedding_fingerprint = Column(String, nullable=False)
    candidate_matches = Column(Text, nullable=True)        # JSON list of candidates
    decision_tier = Column(String, nullable=False)
    selected_identity = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    decision_timestamp = Column(DateTime, nullable=False)
    sync_event_id = Column(String, nullable=True)
    provenance_chain_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    detection = relationship("Detection", back_populates="provenance")


class CameraConfig(Base):
    """Versioned adaptive recognition configuration per camera."""
    __tablename__ = "camera_configs"

    id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    detection_threshold = Column(Float, default=0.50)
    recognition_threshold = Column(Float, default=0.35)
    quality_thresholds = Column(Text, nullable=True) # JSON serialized quality dict
    sampling_rate = Column(Integer, default=1) # Frame skip / process interval
    temporal_window = Column(Float, default=3.0) # Temporal window in seconds
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    camera = relationship("Camera", back_populates="configs")


class Alert(Base):
    """Security alert triggered by detection."""
    __tablename__ = "alerts"
    
    id = Column(String, primary_key=True, index=True)
    detection_id = Column(String, ForeignKey("detections.id"), nullable=True, index=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    severity = Column(String)  # critical, high, medium
    reason = Column(String)
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    camera = relationship("Camera", back_populates="alerts")
    detection = relationship("Detection", back_populates="alert")
    profile = relationship("Profile", back_populates="alerts")


class CameraTransition(Base):
    """Observed movement of an identified person between two cameras."""
    __tablename__ = "camera_transitions"

    id = Column(String, primary_key=True, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    from_camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    to_camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    detected_at = Column(DateTime, nullable=False, index=True)
    travel_seconds = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)
    transition_type = Column(String, default="CONFIRMED")  # CONFIRMED, PROBABLE, UNCERTAIN
    similarity = Column(Float, nullable=True)
    temporal_score = Column(Float, nullable=True)
    reasoning_metadata = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    profile = relationship("Profile")
    from_camera = relationship("Camera", foreign_keys=[from_camera_id], back_populates="outgoing_transitions")
    to_camera = relationship("Camera", foreign_keys=[to_camera_id], back_populates="incoming_transitions")


class ModelThreshold(Base):
    """Configurable model thresholds."""
    __tablename__ = "model_thresholds"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    value = Column(Float, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class SequenceAcknowledgment(Base):
    """Track last acknowledged sequence number per device/camera."""
    __tablename__ = "sequence_acknowledgments"
    
    id = Column(String, primary_key=True, index=True)
    device_id = Column(String, nullable=False, index=True)
    camera_id = Column(String, nullable=False, index=True)
    last_acknowledged_sequence = Column(Integer, nullable=False, default=0)
    last_synced_event_id = Column(String, ForeignKey("detections.event_id"), nullable=True)
    last_updated = Column(DateTime, default=utc_now, onupdate=utc_now)
    created_at = Column(DateTime, default=utc_now)
    
    # Composite unique constraint: device + camera pair
    # (implemented via indexes in database)
    
    __table_args__ = (
        # Unique constraint per device/camera
        # Note: PostgreSQL supports unique constraint with multiple columns
        # SQLite needs to use a different approach
    )

