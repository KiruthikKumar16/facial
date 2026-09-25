
from fastapi import APIRouter, File, UploadFile, Form, Depends, Query, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import json

from database import get_db
from models import *
from schemas import *
from config import settings, IST
from dependencies import verify_edge_node

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
def rename_unregistered_subject(subject_id: str, req: UnregisteredSubjectRenameRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    if not subject or not req.display_name.strip():
        raise HTTPException(status_code=404 if not subject else 422, detail="Invalid unregistered subject name" if subject else "Unregistered subject not found")
    subject.display_name = req.display_name.strip()
    db.commit()
    return _subject_response(subject, db)





@router.post("/api/unregistered-subjects/{subject_id}/register", response_model=ProfileResponse)
def register_unregistered_subject(subject_id: str, req: UnregisteredSubjectRegisterRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    if not subject:
        raise HTTPException(status_code=404, detail="Unregistered subject not found")
    try:
        role = ProfileRoleEnum(req.role)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid profile role")
    profile = Profile(id=str(uuid.uuid4()), name=req.name.strip(), role=role, department=req.department, embedding_status=EmbeddingStatusEnum.indexed, embedding_count=1, enrolled_at=datetime.now(IST))
    if not profile.name:
        raise HTTPException(status_code=422, detail="Profile name cannot be empty")
    db.add(profile)
    db.add(Embedding(id=str(uuid.uuid4()), profile_id=profile.id, vector=subject.representative_embedding))
    db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).update({"profile_id": profile.id, "status": DetectionStatusEnum.recognized, "unregistered_subject_id": None})
    subject.status = "registered"
    db.commit()
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)





@router.post("/api/unregistered-subjects/{subject_id}/assign", response_model=ProfileResponse)
def assign_unregistered_subject(subject_id: str, req: UnregisteredSubjectAssignRequest, db: Session = Depends(get_db)):
    subject = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    profile = db.query(Profile).filter(Profile.id == req.profile_id).first()
    if not subject or not profile:
        raise HTTPException(status_code=404, detail="Unregistered subject or profile not found")
    db.query(Detection).filter(Detection.unregistered_subject_id == subject_id).update({"profile_id": profile.id, "status": DetectionStatusEnum.recognized, "unregistered_subject_id": None})
    subject.status = "assigned"
    db.commit()
    return ProfileResponse.model_validate(profile)





@router.post("/api/unregistered-subjects/{subject_id}/merge", response_model=UnregisteredSubjectResponse)
def merge_unregistered_subject(subject_id: str, req: UnregisteredSubjectMergeRequest, db: Session = Depends(get_db)):
    target = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == subject_id, UnregisteredSubject.status == "active").first()
    source = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == req.source_subject_id, UnregisteredSubject.status == "active").first()
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



