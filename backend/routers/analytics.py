
from fastapi import APIRouter, File, UploadFile, Form, Depends, Query, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Any
import uuid

from database import get_db
from models import (
    Camera, Profile, Detection, CameraTransition, Alert, UnregisteredSubject,
    ProfileRole as ProfileRoleEnum, DetectionStatus as DetectionStatusEnum
)
from schemas import (
    MovementNetworkResponse, MovementEdgeResponse,
    DuplicateCandidateResponse, ProfileResponse,
    SubjectTrajectoryResponse, TrajectoryNodeResponse,
    FootfallBucketResponse, DemographicSliceResponse,
    AttendanceRecordFullResponse
)
from config import IST, to_ist, to_ist_iso
from utils import snapshot_tone_for

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/movement-network", response_model=MovementNetworkResponse)
def get_movement_network(hours: int = Query(24), db: Session = Depends(get_db)):
    """Return observed identified-person movement between cameras."""
    start_time = datetime.now(IST) - timedelta(hours=hours)
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
        lastSeen=to_ist(row.last_seen),
        averageTravelSeconds=round(float(row.average_travel_seconds), 1),
    ) for row in rows])



def _get_duplicates_fallback(db: Session) -> list[DuplicateCandidateResponse]:
    """In-memory fallback for SQLite or non-PostgreSQL dialects where pgvector <=> is unavailable."""
    import numpy as np
    profiles = db.query(Profile).filter(Profile.embedding_count > 0).all()
    candidates = []
    seen = set()

    profile_vecs = []
    for p in profiles:
        for emb in p.embeddings:
            if emb.vector:
                try:
                    vec = np.array(emb.vector, dtype=np.float32).flatten()
                    norm = np.linalg.norm(vec)
                    if norm >= 1e-6:
                        profile_vecs.append((p, vec / norm))
                except Exception:
                    continue

    for i in range(len(profile_vecs)):
        p1, v1 = profile_vecs[i]
        for j in range(i + 1, len(profile_vecs)):
            p2, v2 = profile_vecs[j]
            if p1.id == p2.id:
                continue
            pair = tuple(sorted([p1.id, p2.id]))
            if pair in seen:
                continue
            sim = float(np.dot(v1, v2))
            if sim >= 0.90:
                seen.add(pair)
                candidates.append(DuplicateCandidateResponse(
                    id=f"{p1.id}:{p2.id}",
                    profileAId=p1.id,
                    profileAName=p1.name,
                    profileARole=p1.role.value if hasattr(p1.role, 'value') else str(p1.role),
                    profileAAvatarTone=snapshot_tone_for(p1.id),
                    profileBId=p2.id,
                    profileBName=p2.name,
                    profileBRole=p2.role.value if hasattr(p2.role, 'value') else str(p2.role),
                    profileBAvatarTone=snapshot_tone_for(p2.id),
                    cosineSimilarity=round(sim, 4),
                    sharedSightings=0,
                ))
                if len(candidates) >= 20:
                    return candidates
    return candidates


@router.get("/duplicates", response_model=list[DuplicateCandidateResponse])
def get_duplicates(db: Session = Depends(get_db)):
    """Find duplicate profiles using pgvector (with in-memory SQLite fallback)."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return _get_duplicates_fallback(db)

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


@router.get("/trajectory", response_model=SubjectTrajectoryResponse)
def get_trajectory(profileId: str = Query(...), hours: int = Query(24), db: Session = Depends(get_db)):
    start_time = datetime.now(IST) - timedelta(hours=hours) if hours > 0 else None
    
    # 1. Check Profile
    profile = db.query(Profile).filter(
        (Profile.id == profileId) | (func.lower(Profile.name) == func.lower(profileId))
    ).first()
    
    if profile:
        det_query = db.query(Detection).options(joinedload(Detection.camera)).filter(
            Detection.profile_id == profile.id
        )
        if start_time is not None:
            time_bounded = det_query.filter(Detection.timestamp >= start_time).order_by(Detection.timestamp.asc()).all()
            detections = time_bounded if time_bounded else det_query.order_by(Detection.timestamp.asc()).all()
        else:
            detections = det_query.order_by(Detection.timestamp.asc()).all()

        path = [
            TrajectoryNodeResponse(
                cameraId=d.camera_id,
                cameraName=d.camera.name if d.camera else "Unknown",
                zone=d.camera.zone if d.camera else "General",
                timestamp=to_ist(d.timestamp),
                confidence=d.confidence,
                snapshotTone=snapshot_tone_for(d.id),
            )
            for d in detections
        ]
        return SubjectTrajectoryResponse(
            profileId=profile.id,
            profileName=profile.name,
            role=profile.role.value if hasattr(profile.role, 'value') else str(profile.role or "visitor"),
            path=path
        )

    # 2. Check Unregistered Subject
    unreg = db.query(UnregisteredSubject).filter(
        (UnregisteredSubject.id == profileId) | (UnregisteredSubject.display_name == profileId)
    ).first()
    if unreg:
        det_query = db.query(Detection).options(joinedload(Detection.camera)).filter(
            (Detection.unregistered_subject_id == unreg.id) | (Detection.profile_id == unreg.id)
        )
        if start_time is not None:
            time_bounded = det_query.filter(Detection.timestamp >= start_time).order_by(Detection.timestamp.asc()).all()
            detections = time_bounded if time_bounded else det_query.order_by(Detection.timestamp.asc()).all()
        else:
            detections = det_query.order_by(Detection.timestamp.asc()).all()

        path = [
            TrajectoryNodeResponse(
                cameraId=d.camera_id,
                cameraName=d.camera.name if d.camera else "Unknown",
                zone=d.camera.zone if d.camera else "General",
                timestamp=to_ist(d.timestamp),
                confidence=d.confidence,
                snapshotTone=snapshot_tone_for(d.id),
            )
            for d in detections
        ]
        return SubjectTrajectoryResponse(
            profileId=unreg.id,
            profileName=unreg.display_name,
            role="visitor",
            path=path
        )

    raise HTTPException(status_code=404, detail="Subject or profile not found")


def _normalize_datetime_filter(dt: Any) -> Optional[datetime]:
    """Convert input datetime to naive IST timestamp matching database storage."""
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(IST).replace(tzinfo=None)
    return dt


@router.get("/footfall", response_model=list[FootfallBucketResponse])
def get_footfall(
    days: int = Query(7, description="Number of days to look back from today (used if date_from/date_to not provided)"),
    date_from: Optional[datetime] = Query(None, description="Start date (inclusive) in IST"),
    date_to: Optional[datetime] = Query(None, description="End date (inclusive) in IST"),
    source: Optional[str] = Query(None, description="Filter by data source: 'live' or 'archive'"),
    batch_id: Optional[str] = Query(None, description="Filter by specific archive batch ID"),
    db: Session = Depends(get_db)
):
    norm_from = _normalize_datetime_filter(date_from)
    norm_to = _normalize_datetime_filter(date_to)

    # Determine the time range to filter by
    if norm_from is not None or norm_to is not None:
        if norm_from is not None:
            start_time = norm_from
        else:
            start_time = norm_to - timedelta(days=7)

        if norm_to is not None:
            end_time = norm_to
        else:
            end_time = norm_from + timedelta(days=7)
    else:
        if source == "archive" or batch_id:
            start_time = datetime(1970, 1, 1)
            end_time = datetime(2099, 12, 31)
        else:
            # Fall back to default days (converted to naive IST)
            now_ist = datetime.now(IST).replace(tzinfo=None)
            start_time = now_ist - timedelta(days=days)
            end_time = now_ist

    q = db.query(
        Detection.timestamp,
        Detection.status
    ).filter(
        Detection.timestamp >= start_time,
        Detection.timestamp <= end_time
    )
    if source:
        q = q.filter(Detection.source == source)
    if batch_id:
        q = q.filter(Detection.batch_id == batch_id)

    detections = q.all()

    buckets = {}
    for d in detections:
        ts = to_ist(d.timestamp)
        if ts is None:
            continue
            
        hour_str = f"{ts.hour:02d}:00"
        if hour_str not in buckets:
            buckets[hour_str] = {'total': 0, 'recognized': 0, 'unknown': 0}
            
        buckets[hour_str]['total'] += 1
        if d.status == DetectionStatusEnum.recognized:
            buckets[hour_str]['recognized'] += 1
        elif d.status == DetectionStatusEnum.unknown:
            buckets[hour_str]['unknown'] += 1

    final_res = []
    for i in range(24):
        hour_str = f"{i:02d}:00"
        b = buckets.get(hour_str, {'total': 0, 'recognized': 0, 'unknown': 0})
        final_res.append(FootfallBucketResponse(
            hour=hour_str, 
            detections=b['total'], 
            recognized=b['recognized'], 
            unknown=b['unknown']
        ))
    return final_res


@router.get("/age-distribution", response_model=list[DemographicSliceResponse])
def get_age_distribution(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    norm_from = _normalize_datetime_filter(date_from)
    norm_to = _normalize_datetime_filter(date_to)

    subject_id_col = func.coalesce(
        Detection.profile_id,
        Detection.unregistered_subject_id,
        func.concat('unk_', Detection.id)
    ).label("subject_id")

    subq = db.query(subject_id_col, Detection.age).filter(
        Detection.age != None
    )
    if norm_from:
        subq = subq.filter(Detection.timestamp >= norm_from)
    if norm_to:
        subq = subq.filter(Detection.timestamp <= norm_to)
    if source:
        subq = subq.filter(Detection.source == source)
    if batch_id:
        subq = subq.filter(Detection.batch_id == batch_id)
    
    subq = subq.distinct(subject_id_col).subquery()

    results = db.query(subq.c.age, func.count(subq.c.subject_id)).group_by(subq.c.age).all()
    
    buckets = {"18-24": 0, "25-34": 0, "35-44": 0, "45-54": 0, "55+": 0}
    for age, count in results:
        if age < 18: continue
        elif age <= 24: buckets["18-24"] += count
        elif age <= 34: buckets["25-34"] += count
        elif age <= 44: buckets["35-44"] += count
        elif age <= 54: buckets["45-54"] += count
        else: buckets["55+"] += count
        
    return [DemographicSliceResponse(label=k, value=v) for k, v in buckets.items()]


@router.get("/gender-distribution", response_model=list[DemographicSliceResponse])
def get_gender_distribution(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    norm_from = _normalize_datetime_filter(date_from)
    norm_to = _normalize_datetime_filter(date_to)

    subject_id_col = func.coalesce(
        Detection.profile_id,
        Detection.unregistered_subject_id,
        func.concat('unk_', Detection.id)
    ).label("subject_id")

    subq = db.query(subject_id_col, Detection.gender).filter(
        Detection.gender != None
    )
    if norm_from:
        subq = subq.filter(Detection.timestamp >= norm_from)
    if norm_to:
        subq = subq.filter(Detection.timestamp <= norm_to)
    if source:
        subq = subq.filter(Detection.source == source)
    if batch_id:
        subq = subq.filter(Detection.batch_id == batch_id)
    
    subq = subq.distinct(subject_id_col).subquery()

    results = db.query(subq.c.gender, func.count(subq.c.subject_id)).group_by(subq.c.gender).all()
    slices = []
    for gender, count in results:
        if gender:
            label = gender.value.lower() if hasattr(gender, 'value') else str(gender).lower()
            slices.append(DemographicSliceResponse(label=label.capitalize(), value=count))
    return slices


@router.get("/attendance", response_model=list[AttendanceRecordFullResponse])
def get_attendance(
    days: int = Query(7),
    date_from: Optional[datetime] = Query(None, description="Start date (inclusive) in IST"),
    date_to: Optional[datetime] = Query(None, description="End date (inclusive) in IST"),
    source: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    norm_from = _normalize_datetime_filter(date_from)
    norm_to = _normalize_datetime_filter(date_to)

    if norm_from is not None or norm_to is not None:
        if norm_from is not None:
            start_time = norm_from
        else:
            start_time = norm_to - timedelta(days=7)
        if norm_to is not None:
            end_time = norm_to
        else:
            end_time = norm_from + timedelta(days=7)
    else:
        if source == "archive" or batch_id:
            start_time = datetime(1970, 1, 1)
            end_time = datetime(2099, 12, 31)
        else:
            now_ist = datetime.now(IST).replace(tzinfo=None)
            start_time = now_ist - timedelta(days=days)
            end_time = now_ist
    
    att_q = db.query(
        Detection.profile_id,
        Detection.unregistered_subject_id,
        func.min(Detection.timestamp).label('check_in'),
        func.max(Detection.timestamp).label('check_out'),
        func.count(Detection.id).label('total_sightings'),
    ).filter(
        (Detection.profile_id != None) | (Detection.unregistered_subject_id != None),
        Detection.timestamp >= start_time,
        Detection.timestamp <= end_time
    )
    if source:
        att_q = att_q.filter(Detection.source == source)
    if batch_id:
        att_q = att_q.filter(Detection.batch_id == batch_id)

    results = att_q.group_by(Detection.profile_id, Detection.unregistered_subject_id).all()

    if not results:
        return []

    profile_ids = [r.profile_id for r in results if r.profile_id]
    unreg_ids = [r.unregistered_subject_id for r in results if r.unregistered_subject_id]
    
    profiles = {p.id: p for p in db.query(Profile).filter(Profile.id.in_(profile_ids)).all()} if profile_ids else {}
    unregs = {u.id: u for u in db.query(UnregisteredSubject).filter(UnregisteredSubject.id.in_(unreg_ids)).all()} if unreg_ids else {}

    records = []
    
    for row in results:
        if row.profile_id and row.profile_id in profiles:
            p = profiles[row.profile_id]
            records.append(AttendanceRecordFullResponse(
                profileId=p.id,
                profileName=p.name,
                role=p.role.value if hasattr(p.role, 'value') else str(p.role or "visitor"),
                department=p.department,
                checkIn=to_ist(row.check_in),
                checkOut=to_ist(row.check_out),
                totalSightings=int(row.total_sightings or 0),
                avatarTone=snapshot_tone_for(p.id),
            ))
        elif row.unregistered_subject_id and row.unregistered_subject_id in unregs:
            u = unregs[row.unregistered_subject_id]
            records.append(AttendanceRecordFullResponse(
                profileId=u.id,
                profileName=u.display_name,
                role="unknown",
                department=None,
                checkIn=to_ist(row.check_in),
                checkOut=to_ist(row.check_out),
                totalSightings=int(row.total_sightings or 0),
                avatarTone="gray",
            ))
    return records



