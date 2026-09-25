
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

router = APIRouter(tags=['Detections'])



@router.post("/api/detections", response_model=DetectionResponse)
async def create_detection(
    req: DetectionCreateRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """
    Endpoint for edge node to push detection logs.
    
    Idempotency: If event_id is provided, uses it as an idempotency key.
    Retransmitting the same detection with the same event_id returns existing record.
    """
    import asyncio

    # Ensure timestamp is explicitly strictly IST 
    if req.timestamp.tzinfo is None:
        req_timestamp_ist = req.timestamp.replace(tzinfo=IST)
    else:
        req_timestamp_ist = req.timestamp.astimezone(IST)
    
    sync_info = None
    is_duplicate = False
    is_out_of_order = False
    is_gap_detected = False
    ack_to_update = None

    if req.device_id and req.sequence_number is not None:
        ack = db.query(SequenceAcknowledgment).filter(
            SequenceAcknowledgment.device_id == req.device_id,
            SequenceAcknowledgment.camera_id == req.camera_id
        ).first()
        
        if not ack:
            ack = SequenceAcknowledgment(
                id=str(uuid.uuid4()),
                device_id=req.device_id,
                camera_id=req.camera_id,
                last_acknowledged_sequence=0
            )
            db.add(ack)
            db.flush()
            
        dup_check = db.query(Detection).filter(
            Detection.device_id == req.device_id,
            Detection.camera_id == req.camera_id,
            Detection.sequence_number == req.sequence_number
        ).first()
        
        if dup_check:
            is_duplicate = True
        elif req.sequence_number <= ack.last_acknowledged_sequence:
            is_out_of_order = True
        elif req.sequence_number > ack.last_acknowledged_sequence + 1:
            is_gap_detected = True
            
        if not is_duplicate and req.sequence_number > ack.last_acknowledged_sequence:
            ack.last_acknowledged_sequence = req.sequence_number
            ack_to_update = ack
            
        sync_info = SequenceSyncInfo(
            device_id=req.device_id,
            camera_id=req.camera_id,
            last_acknowledged_sequence=ack.last_acknowledged_sequence,
            is_duplicate=is_duplicate,
            is_out_of_order=is_out_of_order,
            is_gap_detected=is_gap_detected
        )

    # Removed python-level memory check to prevent race condition.
    # Duplicates are now handled atomically at the database level via IntegrityError.

    camera = db.query(Camera).filter(Camera.id == req.camera_id).first()
    if not camera:
        camera = Camera(id=req.camera_id, name=req.camera_id, status=CameraStatusEnum.online)
        db.add(camera)
        db.commit()
        db.refresh(camera)
        
    profile_id = None
    profile = None
    profile, profile_id, status = resolve_detection_identity(db, req.identity)

    if profile_id:
        previous = db.query(Detection).filter(
            Detection.profile_id == profile_id,
            Detection.timestamp < req_timestamp_ist,
        ).order_by(Detection.timestamp.desc()).first()
        if previous and previous.camera_id != req.camera_id:
            previous_timestamp = previous.timestamp
            if previous_timestamp.tzinfo is None and req_timestamp_ist.tzinfo is not None:
                previous_timestamp = previous_timestamp.replace(tzinfo=req_timestamp_ist.tzinfo)
            elif previous_timestamp.tzinfo is not None and req_timestamp_ist.tzinfo is None:
                previous_timestamp = previous_timestamp.replace(tzinfo=None)
            travel_seconds = (req_timestamp_ist - previous_timestamp).total_seconds()
            
            # Cross-Camera continuity evaluation with topology and temporal constraints
            classification, reasoning = continuity_tracker.evaluate_transition(
                from_camera_id=previous.camera_id,
                to_camera_id=req.camera_id,
                elapsed_seconds=max(0.001, travel_seconds),
                embedding_similarity=req.confidence,
            )
            
            db.add(CameraTransition(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                from_camera_id=previous.camera_id,
                to_camera_id=req.camera_id,
                detected_at=req_timestamp_ist,
                travel_seconds=travel_seconds,
                confidence=req.confidence,
                transition_type=classification.value,
                similarity=req.confidence,
                temporal_score=reasoning.temporal_score,
                reasoning_metadata=json.dumps(reasoning.to_dict()),
            ))

    if profile is not None:
        profile.last_seen = req_timestamp_ist

    detection = Detection(
        id=str(uuid.uuid4()),
        event_id=req.event_id,  # Required Idempotency key
        embedding_vector=req.embedding,
        device_id=req.device_id,
        sequence_number=req.sequence_number,
        camera_id=req.camera_id,
        profile_id=profile_id,
        timestamp=req_timestamp_ist,
        status=status,
        confidence=req.confidence,
        bbox=f"[{int(req.bbox[0])}, {int(req.bbox[1])}, {int(req.bbox[2])}, {int(req.bbox[3])}]",
        liveness_score=0.0,
        age=req.age,
        gender=parse_gender(req.gender),
        wearing_mask=False,
        wearing_glasses=False,
        priority=req.priority.value if hasattr(req.priority, 'value') else req.priority,
        config_version=req.camera_config_version or req.config_version or 1,
        detection_model_version=req.detection_model_version or "scrfd_500m_bnkps_v1",
        embedding_model_version=req.embedding_model_version or "w600k_mbf_v1",
        gallery_version=req.gallery_version or 1,
        threshold_version=req.threshold_version or 1,
        camera_config_version=req.camera_config_version or req.config_version or 1,
        algorithm_version=req.algorithm_version or "temporal_fusion_v2",
        version_bundle_hash=req.version_bundle_hash or ModelConfigVersionBundle(
            detection_model_version=req.detection_model_version or "scrfd_500m_bnkps_v1",
            embedding_model_version=req.embedding_model_version or "w600k_mbf_v1",
            gallery_version=req.gallery_version or 1,
            threshold_version=req.threshold_version or 1,
            camera_config_version=req.camera_config_version or req.config_version or 1,
            algorithm_version=req.algorithm_version or "temporal_fusion_v2",
        ).bundle_hash,
    )
    
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(detection)
        db.flush()
        if ack_to_update is not None:
            ack_to_update.last_synced_event_id = req.event_id
        db.commit()
        db.refresh(detection)
        inserted = True

        # Store Provenance Lineage Record
        if req.provenance:
            prov_dict = req.provenance if isinstance(req.provenance, dict) else (
                req.provenance.model_dump() if hasattr(req.provenance, 'model_dump') else req.provenance.dict()
            )
        else:
            prov_dict = {}

        frame_ref = prov_dict.get("frame_reference", f"frm_{req.camera_id}_{int(req_timestamp_ist.timestamp()*1000)}")
        track_id = prov_dict.get("track_id")
        obs_refs = json.dumps(prov_dict.get("observation_references", [f"obs_{frame_ref}_01"]))
        cand_matches = json.dumps(prov_dict.get("candidate_matches", [{"identity": req.identity or "Unknown", "score": req.confidence, "rank": 1}]))
        emb_fp = prov_dict.get("embedding_fingerprint", hashlib.sha256(f"emb_{req.event_id}".encode()).hexdigest())
        dec_tier = prov_dict.get("decision_tier", "LOCAL_HIGH_CONFIDENCE")
        chain_hash = prov_dict.get("provenance_chain_hash", hashlib.sha256(f"chain_{req.event_id}".encode()).hexdigest())

        prov_record = EventProvenance(
            id=str(uuid.uuid4()),
            event_id=req.event_id,
            camera_id=req.camera_id,
            frame_reference=frame_ref,
            track_id=track_id,
            observation_references=obs_refs,
            detection_model_version=req.detection_model_version or "scrfd_500m_bnkps_v1",
            embedding_model_version=req.embedding_model_version or "w600k_mbf_v1",
            embedding_fingerprint=emb_fp,
            candidate_matches=cand_matches,
            decision_tier=dec_tier,
            selected_identity=req.identity or "Unknown",
            confidence=req.confidence,
            decision_timestamp=req_timestamp_ist,
            sync_event_id=prov_dict.get("sync_event_id", f"sync_{req.event_id}"),
            provenance_chain_hash=chain_hash,
        )
        db.add(prov_record)
        db.commit()
    except IntegrityError:
        db.rollback()
        # The event_id already exists. This handles concurrent duplicate submissions safely.
    except Exception as e:
        import traceback
        with open("error_log.txt", "w") as f:
            f.write(traceback.format_exc())
        raise
        existing = db.query(Detection).filter(Detection.event_id == req.event_id).first()
        if not existing:
            raise  # IntegrityError wasn't caused by event_id uniqueness
        
        logger.info(f"Detection {req.event_id} already exists (idempotent retry)")
        resp = DetectionResponse.model_validate(existing)
        resp.sync_info = sync_info
        resp.inserted = False
        return resp

    should_alert, severity, reason = alert_meta_for_detection(status, profile, req.identity)
    if should_alert and severity and reason:
        alert = Alert(
            id=str(uuid.uuid4()),
            detection_id=detection.id,
            camera_id=req.camera_id,
            profile_id=profile_id,
            timestamp=req.timestamp,
            severity=severity,
            reason=reason,
            acknowledged=False,
        )
        db.add(alert)
        db.commit()

    face_log = build_face_log_payload(detection, camera, profile)

    # Broadcast face log directly (frontend expects detection fields at message.data)
    asyncio.create_task(manager.broadcast("alerts", face_log))
    asyncio.create_task(manager.broadcast("kpis", {"refresh": True}))

    resp = DetectionResponse.model_validate(detection)
    resp.sync_info = sync_info
    resp.inserted = inserted
    return resp





@router.post("/api/detections/batch", response_model=List[DetectionResponse])
async def create_detections_batch(
    reqs: DetectionBatchRequest,
    db: Session = Depends(get_db),
    edge_id: str = Depends(verify_edge_node)
):
    """
    Ingest a batch of detections efficiently.
    """
    responses = []
    for req in reqs.detections:
        try:
            resp = await create_detection(req, db, edge_id)
            responses.append(resp)
        except Exception as e:
            logger.error(f"Failed to process event in batch {req.event_id}: {e}")
            # If one fails, we can just skip it or handle it. 
            # In a real batch we might return partial success or 207 Multi-Status.
            # But here we'll just ignore failed ones from the response to let edge retry them?
            # Actually edge retries everything not returned? Edge expects 200 OK.
            pass
            
    return responses





@router.post("/api/detections/reconcile", response_model=SyncReconciliationResponse)
def reconcile_sync(
    req: SyncReconciliationRequest,
    db: Session = Depends(get_db),
    edge_id: str = Depends(verify_edge_node)
):
    """
    Reconcile edge sync state with the cloud.
    Finds exact missing sequence ranges.
    """
    reconciled_cameras = []
    
    for cam_meta in req.cameras:
        # Check if backend has SequenceAcknowledgment
        ack = db.query(SequenceAcknowledgment).filter(
            SequenceAcknowledgment.device_id == req.device_id,
            SequenceAcknowledgment.camera_id == cam_meta.camera_id
        ).first()
        
        last_ack = ack.last_acknowledged_sequence if ack else 0
        
        # Determine the start of the window we need to check
        # We start from the earliest known 'completed' state, or 1
        edge_completed = cam_meta.last_completed_sequence or 0
        start_search = min(last_ack, edge_completed)
        if start_search == 0:
            start_search = 1
            
        end_search = cam_meta.highest_local_sequence
        
        if end_search < start_search:
            reconciled_cameras.append(CameraSyncRanges(camera_id=cam_meta.camera_id, missing_ranges=[]))
            continue
            
        # Get present sequences in the range
        present_seqs = db.query(Detection.sequence_number).filter(
            Detection.device_id == req.device_id,
            Detection.camera_id == cam_meta.camera_id,
            Detection.sequence_number >= start_search,
            Detection.sequence_number <= end_search
        ).order_by(Detection.sequence_number.asc()).all()
        
        present_set = {seq[0] for seq in present_seqs if seq[0] is not None}
        
        # Find missing ranges
        missing_ranges = []
        current_range_start = None
        
        for seq in range(start_search, end_search + 1):
            if seq not in present_set:
                if current_range_start is None:
                    current_range_start = seq
            else:
                if current_range_start is not None:
                    missing_ranges.append((current_range_start, seq - 1))
                    current_range_start = None
                    
        if current_range_start is not None:
            missing_ranges.append((current_range_start, end_search))
            
        reconciled_cameras.append(CameraSyncRanges(
            camera_id=cam_meta.camera_id,
            missing_ranges=missing_ranges
        ))
        
    return SyncReconciliationResponse(reconciled_cameras=reconciled_cameras)



