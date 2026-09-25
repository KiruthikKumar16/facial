
from fastapi import APIRouter, Depends, Query, HTTPException, Request, Response, File, UploadFile, Form
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

router = APIRouter(tags=['Forensic'])



# ==================== Recognition Provenance Endpoints ====================

@router.get("/api/detections/{event_id}/provenance", response_model=ProvenanceResponse)
def get_detection_provenance(
    event_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve full 7-stage recognition lineage graph and audit provenance for an event.
    (Camera -> Frame -> Track -> Embedding Fingerprint -> Candidates -> Decision -> Cloud Sync)
    """
    det = None
    prov = db.query(EventProvenance).filter(EventProvenance.event_id == event_id).first()
    if not prov:
        # The dashboard may provide either the detection UUID or event_id.
        det = db.query(Detection).filter(Detection.event_id == event_id).first()
        if not det:
            det = db.query(Detection).filter(Detection.id == event_id).first()
        if det:
            prov = db.query(EventProvenance).filter(EventProvenance.event_id == det.event_id).first()

    if not prov:
        # Check if detection exists to synthesize default provenance if legacy
        if not det:
            det = db.query(Detection).filter(Detection.event_id == event_id).first()
        if not det:
            raise HTTPException(status_code=404, detail="Recognition event provenance not found")
        
        # Synthesize fallback provenance
        frame_ref = f"frm_{det.camera_id}_{int(det.timestamp.timestamp()*1000)}"
        emb_fp = hashlib.sha256(f"emb_{det.event_id}".encode()).hexdigest()
        candidates = [{"identity": det.identity or "Unknown", "score": det.confidence or 0.0, "rank": 1}]
        obs_refs = [f"obs_{frame_ref}_01"]
        chain_hash = hashlib.sha256(f"chain_{det.event_id}".encode()).hexdigest()
        
        stages = [
            ProvenanceStageResponse(stage_name="1. Camera Ingestion", stage_id=f"cam_{det.camera_id}", timestamp=det.timestamp.timestamp(), metadata={"camera_id": det.camera_id}),
            ProvenanceStageResponse(stage_name="2. Frame Acquisition", stage_id=frame_ref, timestamp=det.timestamp.timestamp(), metadata={"frame_reference": frame_ref}),
            ProvenanceStageResponse(stage_name="3. Face Tracking", stage_id="track_untracked", timestamp=det.timestamp.timestamp(), metadata={"track_id": None}),
            ProvenanceStageResponse(stage_name="4. Embedding Extraction", stage_id=f"emb_{emb_fp[:12]}", timestamp=det.timestamp.timestamp(), metadata={"embedding_fingerprint": emb_fp}),
            ProvenanceStageResponse(stage_name="5. Candidate Evaluation", stage_id=f"eval_{det.event_id}", timestamp=det.timestamp.timestamp(), metadata={"candidates": candidates}),
            ProvenanceStageResponse(stage_name="6. Recognition Decision", stage_id=f"dec_{det.event_id}", timestamp=det.timestamp.timestamp(), metadata={"selected_identity": det.identity, "confidence": det.confidence}),
            ProvenanceStageResponse(stage_name="7. Cloud Synchronization", stage_id=f"sync_{det.event_id}", timestamp=det.timestamp.timestamp(), metadata={"cloud_detection_id": det.id}),
        ]
        
        return ProvenanceResponse(
            event_id=det.event_id,
            detection_id=det.id,
            camera_id=det.camera_id,
            camera_config_version=det.camera_config_version or det.config_version or 1,
            frame_reference=frame_ref,
            track_id=None,
            observation_references=obs_refs,
            detection_model_version=det.detection_model_version or "scrfd_500m_bnkps_v1",
            embedding_model_version=det.embedding_model_version or "w600k_mbf_v1",
            embedding_fingerprint=emb_fp,
            candidate_matches=[ProvenanceCandidateResponse(**c) for c in candidates],
            decision_tier="LOCAL_HIGH_CONFIDENCE",
            selected_identity=det.identity or "Unknown",
            confidence=det.confidence or 0.0,
            decision_timestamp=det.timestamp,
            sync_event_id=f"sync_{det.event_id}",
            cloud_record_id=det.id,
            provenance_chain_hash=chain_hash,
            stages=stages,
        )

    # Parse stored JSON fields
    obs_list = json.loads(prov.observation_references) if prov.observation_references else []
    cand_list = json.loads(prov.candidate_matches) if prov.candidate_matches else []
    det = db.query(Detection).filter(Detection.event_id == prov.event_id).first()
    
    stages = [
        ProvenanceStageResponse(stage_name="1. Camera Ingestion", stage_id=f"cam_{prov.camera_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"camera_id": prov.camera_id}),
        ProvenanceStageResponse(stage_name="2. Frame Acquisition", stage_id=prov.frame_reference, timestamp=prov.decision_timestamp.timestamp(), metadata={"frame_reference": prov.frame_reference, "obs_count": len(obs_list)}),
        ProvenanceStageResponse(stage_name="3. Face Tracking", stage_id=prov.track_id or "untracked", timestamp=prov.decision_timestamp.timestamp(), metadata={"track_id": prov.track_id, "observations": obs_list}),
        ProvenanceStageResponse(stage_name="4. Embedding Extraction", stage_id=f"emb_{prov.embedding_fingerprint[:12]}", timestamp=prov.decision_timestamp.timestamp(), metadata={"embedding_fingerprint": prov.embedding_fingerprint, "model": prov.embedding_model_version}),
        ProvenanceStageResponse(stage_name="5. Candidate Evaluation", stage_id=f"eval_{prov.event_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"candidates": cand_list}),
        ProvenanceStageResponse(stage_name="6. Recognition Decision", stage_id=f"dec_{prov.event_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"selected_identity": prov.selected_identity, "confidence": prov.confidence, "tier": prov.decision_tier}),
        ProvenanceStageResponse(stage_name="7. Cloud Synchronization", stage_id=prov.sync_event_id or f"sync_{prov.event_id}", timestamp=prov.decision_timestamp.timestamp(), metadata={"chain_hash": prov.provenance_chain_hash}),
    ]

    return ProvenanceResponse(
        event_id=prov.event_id,
        detection_id=det.id if det else None,
        camera_id=prov.camera_id,
        camera_config_version=(det.camera_config_version or det.config_version or 1) if det else 1,
        frame_reference=prov.frame_reference,
        track_id=prov.track_id,
        observation_references=obs_list,
        detection_model_version=prov.detection_model_version,
        embedding_model_version=prov.embedding_model_version,
        embedding_fingerprint=prov.embedding_fingerprint,
        candidate_matches=[ProvenanceCandidateResponse(**c) for c in cand_list],
        decision_tier=prov.decision_tier,
        selected_identity=prov.selected_identity,
        confidence=prov.confidence,
        decision_timestamp=prov.decision_timestamp,
        sync_event_id=prov.sync_event_id,
        cloud_record_id=det.id if det else None,
        provenance_chain_hash=prov.provenance_chain_hash,
        stages=stages,
    )





@router.post("/api/provenance/retention", response_model=ProvenanceRetentionResponse)
def enforce_provenance_retention(
    req: ProvenanceRetentionRequest,
    db: Session = Depends(get_db),
):
    """
    Enforce data retention policy on intermediate provenance records.
    Purges historical processing lineage older than max_retention_days while retaining the detection.
    """
    from datetime import timedelta
    cutoff = datetime.now(IST) - timedelta(days=req.max_retention_days)
    
    # Count & delete expired records
    expired_records = db.query(EventProvenance).filter(EventProvenance.created_at < cutoff).all()
    count = len(expired_records)
    for r in expired_records:
        db.delete(r)
    db.commit()
    
    remaining_count = db.query(EventProvenance).count()
    return ProvenanceRetentionResponse(
        purged_records_count=count,
        retained_records_count=remaining_count,
        cutoff_timestamp=cutoff,
    )





@router.post("/api/internal/forensic/search-vector", response_model=list[ForensicMatchResponse])
def run_forensic_vector_search(
    req: ForensicVectorSearchRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    """Run forensic search from a probe embedding generated by an edge node."""
    return run_forensic_vector_query(
        db=db,
        target_embedding=[float(v) for v in req.embedding],
        threshold=req.threshold,
        date_from=req.date_from,
        date_to=req.date_to,
        camera_ids=req.camera_ids,
        gender=req.gender,
        age_min=req.age_min,
        age_max=req.age_max,
        wearing_mask=req.wearing_mask,
        wearing_glasses=req.wearing_glasses,
    )





@router.post("/api/forensic/search", response_model=list[ForensicMatchResponse])
async def run_forensic_search(
    image: UploadFile = File(None),
    profile_id: Optional[str] = Form(None),
    threshold: float = Form(0.60),
    date_from: Optional[datetime] = Form(None),
    date_to: Optional[datetime] = Form(None),
    camera_ids: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    age_min: Optional[int] = Form(None),
    age_max: Optional[int] = Form(None),
    wearing_mask: Optional[bool] = Form(None),
    wearing_glasses: Optional[bool] = Form(None),
    db: Session = Depends(get_db)
):
    """Run forensic search using pgvector."""
    if not image and not profile_id:
        raise HTTPException(status_code=400, detail="Upload a probe image or select a known vector to run forensic search.")

    target_embedding = None
    if image:
        if not ai_models.get("detector"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Forensic image search is not enabled on this backend. "
                    "Run the backend locally, or set ENABLE_FORENSIC_SEARCH=true "
                    "on Render and redeploy."
                ),
            )
        target_embedding_raw = await extract_face_embedding(image)
        if target_embedding_raw is None:
            raise HTTPException(
                status_code=422,
                detail="No face embedding could be extracted from the uploaded image.",
            )
        target_embedding = target_embedding_raw.tolist()
    else:
        # Load embedding from known profile/vector
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if profile and profile.embeddings:
            target_embedding = profile.embeddings[0].vector
        else:
            unreg = db.query(UnregisteredSubject).filter(UnregisteredSubject.id == profile_id).first()
            if unreg and unreg.representative_embedding is not None:
                target_embedding = unreg.representative_embedding
            else:
                raise HTTPException(status_code=404, detail="Selected vector not found or has no embedding.")

    return run_forensic_vector_query(
        db=db,
        target_embedding=list(target_embedding),
        threshold=threshold,
        date_from=date_from,
        date_to=date_to,
        camera_ids=[
            camera_id.strip()
            for camera_id in (camera_ids or "").split(",")
            if camera_id.strip()
        ],
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        wearing_mask=wearing_mask,
        wearing_glasses=wearing_glasses,
    )


