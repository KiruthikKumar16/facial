
from fastapi import APIRouter, File, UploadFile, Form, Depends, Query, HTTPException, Request, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract, text, case, select, or_
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import json

from database import get_db
from models import *
from schemas import *
from config import settings, IST, to_ist_iso
from dependencies import verify_edge_node
from utils import snapshot_tone_for

router = APIRouter(tags=['Logs & Alerts'])


# ==================== Detection/Log Endpoints ====================

@router.get("/api/logs", response_model=list[FaceLogResponse])
def get_logs(
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    source: Optional[str] = Query(None, description="Filter by data source: 'live' or 'archive'"),
    batch_id: Optional[str] = Query(None, description="Filter by specific archive batch ID"),
    db: Session = Depends(get_db)
):
    """Get face detection logs."""
    query = db.query(Detection).options(
        joinedload(Detection.camera),
        joinedload(Detection.profile),
        joinedload(Detection.unregistered_subject),
    )
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)
    if source:
        query = query.filter(Detection.source == source)
    if batch_id:
        query = query.filter(Detection.batch_id == batch_id)

    detections = query.order_by(
        Detection.timestamp.desc()
    ).limit(limit).offset(offset).all()
    
    results = []
    
    for i, det in enumerate(detections):
        resolved_name = None
        if det.profile:
            resolved_name = det.profile.name
        elif det.unregistered_subject and det.unregistered_subject.display_name:
            resolved_name = det.unregistered_subject.display_name

        results.append(FaceLogResponse(
            id=det.id,
            camera_id=det.camera_id,
            camera_name=det.camera.name if det.camera else "Unknown",
            timestamp=to_ist_iso(det.timestamp),
            status=det.status.value,
            confidence=det.confidence,
            liveness_score=det.liveness_score,
            profile_id=det.profile_id or (det.unregistered_subject.id if det.unregistered_subject else None),
            profile_name=resolved_name,
            role=det.profile.role.value if det.profile else None,
            age=det.age or 0,
            gender=det.gender.value if det.gender else "unknown",
            wearing_mask=det.wearing_mask,
            wearing_glasses=det.wearing_glasses,
            snapshot_tone=snapshot_tone_for(det.id),
            face_image=det.face_image,
            source=det.source.value if hasattr(det.source, "value") else str(det.source or "live"),
            batch_id=det.batch_id,
            source_video=det.device_id,
            video_elapsed_sec=float(det.sequence_number) if det.sequence_number is not None else None,
        ))
    
    return results


def _compute_direction(first_bbox_str: Optional[str], last_bbox_str: Optional[str]) -> str:
    """Classify spatial body movement direction across camera FOV from entry and exit bounding boxes."""
    if not first_bbox_str or not last_bbox_str:
        return "Stationary / Present"
    try:
        b1 = json.loads(first_bbox_str) if isinstance(first_bbox_str, str) else first_bbox_str
        b2 = json.loads(last_bbox_str) if isinstance(last_bbox_str, str) else last_bbox_str
        if len(b1) >= 4 and len(b2) >= 4:
            cx1 = (float(b1[0]) + float(b1[2])) / 2.0
            cx2 = (float(b2[0]) + float(b2[2])) / 2.0
            w1 = float(b1[2]) - float(b1[0])
            w2 = float(b2[2]) - float(b2[0])
            dx = cx2 - cx1
            dw = w2 - w1
            if abs(dx) > 35:
                return "Left → Right Passage" if dx > 0 else "Right → Left Passage"
            elif dw > 25:
                return "Inbound / Approaching"
            elif dw < -25:
                return "Outbound / Receding"
            else:
                return "Stationary Dwell"
    except Exception:
        pass
    return "Stationary / Present"


@router.get("/api/logs/episodes", response_model=list[CameraEpisodeResponse])
def get_camera_episodes(
    limit: int = Query(100, le=500),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    source: Optional[str] = Query(None, description="Filter by data source: 'live' or 'archive'"),
    batch_id: Optional[str] = Query(None, description="Filter by specific archive batch ID"),
    profile_id: Optional[str] = Query(None, description="Filter by profile or unregistered subject ID"),
    gap_threshold: float = Query(45.0, ge=1.0, le=300.0, description="Max seconds gap between detections in the same episode"),
    min_dwell: float = Query(0.0, ge=0.0, le=300.0, description="Minimum dwell duration in seconds"),
    min_confidence: float = Query(0.0, ge=0.0, le=100.0, description="Minimum peak confidence percentage"),
    db: Session = Depends(get_db)
):
    """Get aggregated camera passage & In/Out presence episodes.
    
    Instead of flooding with raw frame-by-frame logs or sub-second fragments,
    groups continuous detections into distinct presence episodes tracking
    Entry (IN), Exit (OUT), Dwell Duration, Body Flow, and Transit Handoffs.
    """
    query = db.query(Detection).options(
        joinedload(Detection.camera),
        joinedload(Detection.profile),
        joinedload(Detection.unregistered_subject),
    )
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)
    if source:
        query = query.filter(Detection.source == source)
    if batch_id:
        query = query.filter(Detection.batch_id == batch_id)
    if profile_id:
        query = query.filter(
            or_(
                Detection.profile_id == profile_id,
                Detection.unregistered_subject_id == profile_id
            )
        )

    detections = query.order_by(Detection.timestamp.asc()).all()
    if not detections:
        return []

    # Partition by (camera_id, subject_key)
    camera_subject_map: Dict[tuple, List[Detection]] = {}
    for d in detections:
        if d.profile_id:
            s_key = f"prof:{d.profile_id}"
        elif d.unregistered_subject_id:
            s_key = f"unreg:{d.unregistered_subject_id}"
        else:
            s_key = f"raw:{d.id}"
        key = (d.camera_id, s_key)
        if key not in camera_subject_map:
            camera_subject_map[key] = []
        camera_subject_map[key].append(d)

    raw_episodes = []
    for (cam_id, s_key), det_list in camera_subject_map.items():
        det_list.sort(key=lambda x: x.timestamp)
        current_cluster: List[Detection] = []
        for d in det_list:
            if not current_cluster:
                current_cluster.append(d)
            else:
                prev = current_cluster[-1]
                gap = (d.timestamp - prev.timestamp).total_seconds()
                if gap <= gap_threshold:
                    current_cluster.append(d)
                else:
                    raw_episodes.append(current_cluster)
                    current_cluster = [d]
        if current_cluster:
            raw_episodes.append(current_cluster)

    # Convert to episode objects
    now_dt = datetime.now()
    parsed_episodes = []
    for cluster in raw_episodes:
        first = cluster[0]
        last = cluster[-1]
        
        # Real dwell duration: 0.0s if 1 detection blip, real seconds if multi-frame
        raw_dwell = round((last.timestamp - first.timestamp).total_seconds(), 1)
        dwell = raw_dwell if len(cluster) > 1 else 0.0

        peak_conf = max((float(d.confidence) for d in cluster if d.confidence is not None), default=0.0)

        # Minimum dwell and confidence filters
        if min_dwell > 0.0 and dwell < min_dwell:
            continue
        if min_confidence > 0.0 and peak_conf < min_confidence:
            continue
        
        # Identity resolution
        resolved_name = "Unidentified"
        resolved_subject_id = None
        role_val = "visitor"
        if first.profile:
            resolved_name = first.profile.name
            resolved_subject_id = first.profile.id
            role_val = first.profile.role.value if hasattr(first.profile.role, 'value') else str(first.profile.role or "visitor")
        elif first.unregistered_subject:
            resolved_name = first.unregistered_subject.display_name or f"Subject {first.unregistered_subject.id[:8]}"
            resolved_subject_id = first.unregistered_subject.id
            role_val = "visitor"
        else:
            resolved_name = f"Subject {first.id[:8]}"
            resolved_subject_id = first.id

        is_flagged = any(d.status == DetectionStatus.flagged for d in cluster)
        status_val = "flagged" if is_flagged else ("recognized" if first.profile_id else "unknown")
        liveness_val = max((float(d.liveness_score) for d in cluster if d.liveness_score is not None), default=0.0)
        direction_val = "Instant Glance" if len(cluster) == 1 else _compute_direction(first.bbox, last.bbox)

        cam_name = first.camera.name if first.camera else first.camera_id
        cam_zone = first.camera.zone if first.camera else "General"
        src_val = first.source.value if hasattr(first.source, 'value') else str(first.source or "live")

        is_live_active = (src_val == "live") and ((now_dt - last.timestamp).total_seconds() < 12.0)
        ep_id = f"ep-{first.camera_id}-{resolved_subject_id or 'anon'}-{first.timestamp.strftime('%Y%m%d%H%M%S')}"

        parsed_episodes.append({
            "id": ep_id,
            "camera_id": first.camera_id,
            "camera_name": cam_name,
            "zone": cam_zone,
            "subject_id": resolved_subject_id,
            "subject_name": resolved_name,
            "role": role_val,
            "status": status_val,
            "in_time": to_ist_iso(first.timestamp),
            "out_time": to_ist_iso(last.timestamp),
            "in_dt": first.timestamp,
            "out_dt": last.timestamp,
            "dwell_seconds": dwell,
            "detection_count": len(cluster),
            "peak_confidence": peak_conf,
            "liveness_score": liveness_val,
            "in_face_image": first.face_image or last.face_image,
            "out_face_image": last.face_image or first.face_image,
            "direction": direction_val,
            "source": src_val,
            "batch_id": first.batch_id,
            "snapshot_tone": snapshot_tone_for(first.id),
            "is_active": is_live_active,
            "next_camera_id": None,
            "next_camera_name": None,
            "transit_seconds": None,
            "detection_ids": [d.id for d in cluster]
        })

    # Inter-camera transition detection per subject
    by_subj: Dict[str, list] = {}
    for ep in parsed_episodes:
        s_id = ep["subject_id"] or ep["subject_name"]
        if s_id not in by_subj:
            by_subj[s_id] = []
        by_subj[s_id].append(ep)

    for s_id, s_eps in by_subj.items():
        s_eps.sort(key=lambda x: x["in_dt"])
        for idx in range(len(s_eps) - 1):
            curr_ep = s_eps[idx]
            next_ep = s_eps[idx + 1]
            if curr_ep["camera_id"] != next_ep["camera_id"]:
                transit = (next_ep["in_dt"] - curr_ep["out_dt"]).total_seconds()
                if 0 <= transit <= 900.0:  # within 15 mins
                    curr_ep["next_camera_id"] = next_ep["camera_id"]
                    curr_ep["next_camera_name"] = next_ep["camera_name"]
                    curr_ep["transit_seconds"] = round(transit, 1)

    # Sort all episodes by in_time desc (newest first)
    parsed_episodes.sort(key=lambda x: x["in_dt"], reverse=True)
    results = [
        CameraEpisodeResponse(
            id=ep["id"],
            camera_id=ep["camera_id"],
            camera_name=ep["camera_name"],
            zone=ep["zone"],
            subject_id=ep["subject_id"],
            subject_name=ep["subject_name"],
            role=ep["role"],
            status=ep["status"],
            in_time=ep["in_time"],
            out_time=ep["out_time"],
            dwell_seconds=ep["dwell_seconds"],
            detection_count=ep["detection_count"],
            peak_confidence=ep["peak_confidence"],
            liveness_score=ep["liveness_score"],
            in_face_image=ep["in_face_image"],
            out_face_image=ep["out_face_image"],
            direction=ep["direction"],
            source=ep["source"],
            batch_id=ep["batch_id"],
            snapshot_tone=ep["snapshot_tone"],
            is_active=ep["is_active"],
            next_camera_id=ep["next_camera_id"],
            next_camera_name=ep["next_camera_name"],
            transit_seconds=ep["transit_seconds"],
            detection_ids=ep["detection_ids"],
        )
        for ep in parsed_episodes[:limit]
    ]

    return results





# ==================== Alert Endpoints ====================

@router.get("/api/alerts", response_model=list[AlertResponse])
def get_alerts(
    limit: int = Query(50, le=500),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    source: Optional[str] = Query(None, description="Filter by data source: 'live' or 'archive'"),
    batch_id: Optional[str] = Query(None, description="Filter by specific archive batch ID"),
    db: Session = Depends(get_db)
):
    """Get recent alerts."""
    query = db.query(Alert).options(
        joinedload(Alert.camera),
        joinedload(Alert.profile),
        joinedload(Alert.detection),
    )
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)
    if source:
        query = query.filter(Alert.source == source)
    if batch_id:
        query = query.filter(Alert.batch_id == batch_id)

    alerts = query.order_by(
        Alert.timestamp.desc()
    ).limit(limit).all()
    
    results = []
    
    for i, alert in enumerate(alerts):
        results.append(AlertResponse(
            id=alert.id,
            log_id=alert.detection_id or "",
            camera_id=alert.camera_id,
            camera_name=alert.camera.name if alert.camera else "Unknown",
            timestamp=to_ist_iso(alert.timestamp),
            severity=alert.severity,
            reason=alert.reason,
            profile_id=alert.profile_id,
            profile_name=alert.profile.name if alert.profile else "Unknown",
            role=alert.profile.role.value if alert.profile else "unknown",
            confidence=alert.detection.confidence if alert.detection else 0.0,
            acknowledged=alert.acknowledged,
            snapshot_tone=snapshot_tone_for(alert.id),
            source=alert.source.value if hasattr(alert.source, "value") else str(alert.source or "live"),
            batch_id=alert.batch_id,
        ))
    
    return results





@router.post("/api/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: str,
    req: AlertAcknowledgeRequest,
    db: Session = Depends(get_db)
):
    """Acknowledge an alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.acknowledged = req.acknowledged
    db.commit()
    
    return AlertResponse(
        id=alert.id,
        log_id=alert.detection_id or "",
        camera_id=alert.camera_id,
        camera_name=alert.camera.name if alert.camera else "Unknown",
        timestamp=to_ist_iso(alert.timestamp),
        severity=alert.severity,
        reason=alert.reason,
        profile_id=alert.profile_id,
        profile_name=alert.profile.name if alert.profile else "Unknown",
        role=alert.profile.role.value if alert.profile else "unknown",
        confidence=alert.detection.confidence if alert.detection else 0.0,
        acknowledged=alert.acknowledged,
        snapshot_tone="sky",
    )



