"""SQLAlchemy ORM models for facial recognition system."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector
from database import Base
import enum


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
    last_heartbeat = Column(DateTime, default=datetime.utcnow)
    detections_today = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    detections = relationship("Detection", back_populates="camera")
    alerts = relationship("Alert", back_populates="camera")


class Profile(Base):
    """Known identity in the gallery."""
    __tablename__ = "profiles"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    role = Column(SQLEnum(ProfileRole), default=ProfileRole.visitor)
    department = Column(String)
    embedding_status = Column(SQLEnum(EmbeddingStatus), default=EmbeddingStatus.pending)
    embedding_count = Column(Integer, default=0)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    embeddings = relationship("Embedding", back_populates="profile", cascade="all, delete-orphan")
    detections = relationship("Detection", back_populates="profile")


class Embedding(Base):
    """Face embedding vector (pgvector)."""
    __tablename__ = "embeddings"
    
    id = Column(String, primary_key=True, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    vector = Column(Vector(512), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    profile = relationship("Profile", back_populates="embeddings")


class Detection(Base):
    """Individual face detection event."""
    __tablename__ = "detections"
    
    id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    status = Column(SQLEnum(DetectionStatus), default=DetectionStatus.unknown)
    confidence = Column(Float, default=0.0)
    liveness_score = Column(Float, default=0.0)
    age = Column(Integer)
    gender = Column(SQLEnum(Gender), default=Gender.unknown)
    wearing_mask = Column(Boolean, default=False)
    wearing_glasses = Column(Boolean, default=False)
    bbox = Column(String)  # JSON serialized [x1, y1, x2, y2]
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    camera = relationship("Camera", back_populates="detections")
    profile = relationship("Profile", back_populates="detections")
    alert = relationship("Alert", back_populates="detection", uselist=False)


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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    camera = relationship("Camera", back_populates="alerts")
    detection = relationship("Detection", back_populates="alert")


class ModelThreshold(Base):
    """Configurable model thresholds."""
    __tablename__ = "model_thresholds"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    value = Column(Float, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
