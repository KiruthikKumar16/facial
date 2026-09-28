import hashlib
import uuid
from typing import Optional, Tuple, Any, Dict
from sqlalchemy.orm import Session

from models import (
    Profile, Detection, Camera,
    DetectionStatus as DetectionStatusEnum,
    ProfileRole as ProfileRoleEnum,
    Gender as GenderEnum
)

AVATAR_TONES = ['sky', 'amber', 'rose', 'violet', 'emerald', 'cyan', 'orange', 'indigo']

def snapshot_tone_for(key: str) -> str:
    digest = hashlib.md5(key.encode('utf-8')).hexdigest()
    return AVATAR_TONES[int(digest, 16) % len(AVATAR_TONES)]

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
    normalized = str(value).lower()
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

async def extract_face_embedding(file: Any) -> Optional[Any]:
    """Helper to extract face embedding from uploaded file."""
    try:
        from state import ai_models
        import cv2
        import numpy as np
    except ImportError:
        return None

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
        import logging
        logging.getLogger(__name__).error(f"Error extracting embedding: {e}")
        return None

