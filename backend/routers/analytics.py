
from fastapi import APIRouter, File, UploadFile, Form, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta
from typing import Optional, List
import uuid

from database import get_db
from models import (
    Camera, Profile, Detection, CameraTransition, Alert,
    ProfileRole as ProfileRoleEnum, DetectionStatus as DetectionStatusEnum
)
from schemas import (
    MovementNetworkResponse, MovementEdgeResponse,
    DuplicateCandidateResponse, ProfileResponse,
    SubjectTrajectoryResponse, TrajectoryNodeResponse,
    FootfallBucketResponse, DemographicSliceResponse,
    AttendanceRecordFullResponse
)
from config import IST

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
        lastSeen=row.last_seen,
        averageTravelSeconds=round(float(row.average_travel_seconds), 1),
    ) for row in rows])



@router.get("/duplicates", response_model=list[DuplicateCandidateResponse])
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


@router.get("/trajectory", response_model=SubjectTrajectoryResponse)
def get_trajectory(profileId: str = Query(...), hours: int = Query(24), db: Session = Depends(get_db)):
    start_time = datetime.now(IST) - timedelta(hours=hours)
    
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


@router.get("/footfall", response_model=list[FootfallBucketResponse])
def get_footfall(
    days: int = Query(7, description="Number of days to look back from today (used if date_from/date_to not provided)"),
    date_from: Optional[datetime] = Query(None, description="Start date (inclusive) in IST"),
    date_to: Optional[datetime] = Query(None, description="End date (inclusive) in IST"),
    db: Session = Depends(get_db)
):
    # Determine the time range to filter by
    if date_from is not None or date_to is not None:
        # Use explicit date range if provided
        if date_from is not None:
            start_time = date_from.replace(tzinfo=None)
        else:
            # If only date_to is provided, default to 7 days before date_to
            start_time = date_to.replace(tzinfo=None) - timedelta(days=7)

        if date_to is not None:
            end_time = date_to.replace(tzinfo=None)
        else:
            # If only date_from is provided, default to 7 days after date_from
            end_time = date_from.replace(tzinfo=None) + timedelta(days=7)

        # Adjust end_time to be the end of the day (23:59:59.999999)
        end_time = end_time.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        # Fall back to original behavior for backward compatibility
        start_time = datetime.now(IST) - timedelta(days=days)
        end_time = datetime.now(IST)

    detections = db.query(
        Detection.timestamp,
        Detection.status
    ).filter(
        Detection.timestamp >= start_time,
        Detection.timestamp <= end_time
    ).all()

    buckets = {}
    for d in detections:
        # Ensure timestamp is treated as IST
        if d.timestamp.tzinfo is None:
            ts = d.timestamp.replace(tzinfo=IST)
        else:
            ts = d.timestamp.astimezone(IST)
            
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
    db: Session = Depends(get_db)
):
    # Use DISTINCT ON subject to guarantee each person is counted exactly once, even if age prediction varied
    subject_id_col = func.coalesce(Detection.profile_id, Detection.unregistered_subject_id).label("subject_id")
    subq = db.query(subject_id_col, Detection.age).filter(
        or_(Detection.profile_id != None, Detection.unregistered_subject_id != None),
        Detection.age != None
    )
    if date_from:
        subq = subq.filter(Detection.timestamp >= date_from.replace(tzinfo=None))
    if date_to:
        subq = subq.filter(Detection.timestamp <= date_to.replace(tzinfo=None))
    
    subq = subq.distinct(func.coalesce(Detection.profile_id, Detection.unregistered_subject_id)).subquery()

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
    db: Session = Depends(get_db)
):
    # Use DISTINCT ON subject to guarantee each person is counted exactly once, even if gender prediction varied
    subject_id_col = func.coalesce(Detection.profile_id, Detection.unregistered_subject_id).label("subject_id")
    subq = db.query(subject_id_col, Detection.gender).filter(
        or_(Detection.profile_id != None, Detection.unregistered_subject_id != None),
        Detection.gender != None
    )
    if date_from:
        subq = subq.filter(Detection.timestamp >= date_from.replace(tzinfo=None))
    if date_to:
        subq = subq.filter(Detection.timestamp <= date_to.replace(tzinfo=None))
    
    subq = subq.distinct(func.coalesce(Detection.profile_id, Detection.unregistered_subject_id)).subquery()

    results = db.query(subq.c.gender, func.count(subq.c.subject_id)).group_by(subq.c.gender).all()
    slices = []
    for gender, count in results:
        if gender:
            label = gender.value.capitalize() if hasattr(gender, 'value') else str(gender).capitalize()
            slices.append(DemographicSliceResponse(label=label, value=count))
    return slices


@router.get("/attendance", response_model=list[AttendanceRecordFullResponse])
def get_attendance(
    days: int = Query(7),
    date_from: Optional[datetime] = Query(None, description="Start date (inclusive) in IST"),
    date_to: Optional[datetime] = Query(None, description="End date (inclusive) in IST"),
    db: Session = Depends(get_db)
):
    if date_from is not None or date_to is not None:
        if date_from is not None:
            start_time = date_from.replace(tzinfo=None)
        else:
            start_time = date_to.replace(tzinfo=None) - timedelta(days=7)
        if date_to is not None:
            end_time = date_to.replace(tzinfo=None)
        else:
            end_time = date_from.replace(tzinfo=None) + timedelta(days=7)
        end_time = end_time.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        start_time = datetime.now(IST) - timedelta(days=days)
        end_time = datetime.now(IST)
    
    results = db.query(
        Detection.profile_id,
        Detection.unregistered_subject_id,
        func.min(Detection.timestamp).label('check_in'),
        func.max(Detection.timestamp).label('check_out'),
        func.count(Detection.id).label('total_sightings'),
    ).filter(
        (Detection.profile_id != None) | (Detection.unregistered_subject_id != None),
        Detection.timestamp >= start_time,
        Detection.timestamp <= end_time
    ).group_by(Detection.profile_id, Detection.unregistered_subject_id).all()

    if not results:
        return []

    profile_ids = [r.profile_id for r in results if r.profile_id]
    unreg_ids = [r.unregistered_subject_id for r in results if r.unregistered_subject_id]
    
    profiles = {p.id: p for p in db.query(Profile).filter(Profile.id.in_(profile_ids)).all()} if profile_ids else {}
    from models import UnregisteredSubject
    unregs = {u.id: u for u in db.query(UnregisteredSubject).filter(UnregisteredSubject.id.in_(unreg_ids)).all()} if unreg_ids else {}

    records = []
    
    for row in results:
        if row.profile_id and row.profile_id in profiles:
            p = profiles[row.profile_id]
            records.append(AttendanceRecordFullResponse(
                profileId=p.id,
                profileName=p.name,
                role=p.role.value,
                department=p.department,
                checkIn=row.check_in,
                checkOut=row.check_out,
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
                checkIn=row.check_in,
                checkOut=row.check_out,
                totalSightings=int(row.total_sightings or 0),
                avatarTone="gray",
            ))
    return records



