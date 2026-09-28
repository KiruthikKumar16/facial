
from fastapi import APIRouter, File, UploadFile, Form, Depends, Query, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import json
import hashlib
import numpy as np

from database import get_db
from models import *
from schemas import *
from config import settings, IST
from dependencies import verify_edge_node

def _subject_response(subject: UnregisteredSubject, db: Session) -> UnregisteredSubjectResponse:
    detections = db.query(Detection).filter(
        Detection.unregistered_subject_id == subject.id,
        Detection.profile_id.is_(None),
    ).order_by(Detection.timestamp.asc()).all()
    if not detections:
        first_seen = subject.created_at or datetime.now(IST)
        last_seen = subject.updated_at or first_seen
        cameras = []
        best_conf = 0.0
        event_ids = []
    else:
        first_seen = detections[0].timestamp
        last_seen = detections[-1].timestamp
        cameras = sorted({d.camera_id for d in detections if d.camera_id})
        best_conf = max(float(d.confidence or 0) for d in detections)
        event_ids = [d.event_id or d.id for d in detections]

    emb = subject.representative_embedding
    if emb is not None:
        try:
            emb_list = [float(x) for x in emb]
        except Exception:
            emb_list = []
    else:
        emb_list = []
    fingerprint = hashlib.sha256(json.dumps(emb_list).encode()).hexdigest()
    return UnregisteredSubjectResponse(
        id=subject.id,
        display_name=subject.display_name,
        capture_count=len(detections),
        first_seen=first_seen,
        last_seen=last_seen,
        cameras=cameras,
        best_confidence=best_conf,
        representative_fingerprint=fingerprint,
        vector_dimension=len(emb_list) if emb_list else 512,
        event_ids=event_ids[:100],
        status=subject.status,
    )

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
        Detection.status == DetectionStatus.unknown,
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
                created_at=detection.timestamp,
                updated_at=detection.timestamp,
            )
            db.add(subject)
            subjects.append(subject)
            best_subject = subject

        detection.unregistered_subject_id = best_subject.id
        db.add(detection)
    db.commit()
router = APIRouter(tags=['Unregistered Subjects'])



@router.get("/api/unregistered-subjects", response_model=List[UnregisteredSubjectResponse])
def get_unregistered_subjects(
    threshold: Optional[float] = Query(None, ge=0.5, le=0.99),
    db: Session = Depends(get_db),
):
    _refresh_unregistered_subjects(db, threshold)
    subjects = db.query(UnregisteredSubject).filter(UnregisteredSubject.status == "active").all()
    return [_subject_response(subject, db) for subject in subjects if db.query(Detection).filter(
        Detection.unregistered_subject_id == subject.id, Detection.profile_id.is_(None)
    ).first()]





@router.patch("/api/unregistered-subjects/{subject_id}", response_model=UnregisteredSubjectResponse)
@router.post("/api/unregistered-subjects/{subject_id}/rename", response_model=UnregisteredSubjectResponse)
def rename_unregistered_subject(subject_id: str, req: UnregisteredSubjectRenameRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    new_name = req.resolved_name
    if not subject or not new_name:
        raise HTTPException(status_code=404 if not subject else 422, detail="Invalid unregistered subject name" if subject else "Unregistered subject not found")
    subject.display_name = new_name
    db.commit()
    return _subject_response(subject, db)





@router.post("/api/unregistered-subjects/{subject_id}/register", response_model=ProfileResponse)
def register_unregistered_subject(subject_id: str, req: UnregisteredSubjectRegisterRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    if not subject:
        raise HTTPException(status_code=404, detail="Unregistered subject not found")
    try:
        role = ProfileRole(req.role.lower()) if req.role else ProfileRole.visitor
    except (ValueError, AttributeError):
        role = ProfileRole.visitor
    profile = Profile(id=str(uuid.uuid4()), name=req.name.strip(), role=role, department=req.department, embedding_status=EmbeddingStatus.indexed, embedding_count=1, enrolled_at=datetime.now(IST))
    if not profile.name:
        raise HTTPException(status_code=422, detail="Profile name cannot be empty")
    db.add(profile)
    emb_vec = subject.representative_embedding
    if hasattr(emb_vec, "tolist"):
        emb_vec = emb_vec.tolist()
    db.add(Embedding(id=str(uuid.uuid4()), profile_id=profile.id, vector=emb_vec))
    db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).update({"profile_id": profile.id, "status": DetectionStatus.recognized, "unregistered_subject_id": None})
    subject.status = "registered"
    db.commit()
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)





@router.post("/api/unregistered-subjects/{subject_id}/assign", response_model=ProfileResponse)
def assign_unregistered_subject(subject_id: str, req: UnregisteredSubjectAssignRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    target_profile_id = req.resolved_profile_id
    profile = db.query(Profile).filter(Profile.id == target_profile_id).first()
    if not subject or not profile:
        raise HTTPException(status_code=404, detail="Unregistered subject or profile not found")
    db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).update({"profile_id": profile.id, "status": DetectionStatus.recognized, "unregistered_subject_id": None})
    subject.status = "assigned"
    db.commit()
    return ProfileResponse.model_validate(profile)





@router.post("/api/unregistered-subjects/{subject_id}/merge", response_model=UnregisteredSubjectResponse)
def merge_unregistered_subject(subject_id: str, req: UnregisteredSubjectMergeRequest, db: Session = Depends(get_db)):
    target = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    source_id = req.resolved_source_id
    source = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == source_id, UnregisteredSubject.status == "active").first()
    if not target or not source or target.id == source.id:
        raise HTTPException(status_code=404, detail="Unregistered subject not found")
    db.query(Detection).filter(Detection.unregistered_subject_id == source.id).update({"unregistered_subject_id": target.id})
    source.status = "merged"
    db.commit()
    return _subject_response(target, db)





@router.delete("/api/unregistered-subjects/{subject_id}/events/{event_id}")
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





@router.delete("/api/unregistered-subjects/{subject_id}")
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



