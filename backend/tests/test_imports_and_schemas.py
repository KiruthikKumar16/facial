import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent))

def test_imports():
    """Verify all backend routers, models, schemas, and utils import without circular dependency."""
    import config
    import models
    import schemas
    import utils
    import auth
    import middleware
    import database
    import state
    
    from routers import (
        analytics,
        cameras,
        detections,
        forensic,
        logs,
        profiles,
        system,
        unregistered,
    )
    
    assert config is not None
    assert models is not None
    assert schemas is not None
    assert utils is not None
    assert system.router is not None
    assert detections.router is not None
    assert unregistered.router is not None


def test_schema_validators_and_aliases():
    """Verify Pydantic schemas handle camelCase aliases and field validators."""
    from schemas import (
        UnregisteredSubjectRenameRequest,
        UnregisteredSubjectAssignRequest,
        UnregisteredSubjectMergeRequest,
        VectorSearchMatch,
    )

    rename = UnregisteredSubjectRenameRequest(name="John Doe")
    assert rename.resolved_name == "John Doe"

    rename_camel = UnregisteredSubjectRenameRequest(displayName="Jane Doe")
    assert rename_camel.resolved_name == "Jane Doe"

    assign = UnregisteredSubjectAssignRequest(profileId="profile-123")
    assert assign.resolved_profile_id == "profile-123"

    merge = UnregisteredSubjectMergeRequest(sourceId="source-456")
    assert merge.resolved_source_id == "source-456"

    match = VectorSearchMatch(
        identity="Person 1",
        score=0.95,
        profile_id="p1",
    )
    assert match.profile_id == "p1"
    assert match.identity == "Person 1"

    from schemas import ModelThresholdsResponse
    t_resp = ModelThresholdsResponse.model_validate({
        "recognitionConfidence": 0.85,
        "livenessScore": 0.90,
        "unknownFaceRetentionDays": 45,
    })
    assert t_resp.similarity_confidence == 0.85
    assert t_resp.liveness_threshold == 0.90
    assert t_resp.unknown_face_retention_days == 45


def test_utils_helpers():
    """Verify utils helper functions behave correctly."""
    from utils import parse_gender, alert_meta_for_detection, snapshot_tone_for
    from models import Gender, DetectionStatus

    assert parse_gender("Male") == Gender.male
    assert parse_gender("FEMALE") == Gender.female
    assert parse_gender("unknown_str") == Gender.unknown
    assert parse_gender(None) == Gender.unknown

    tone = snapshot_tone_for("some-arbitrary-id")
    assert tone in ["sky", "amber", "rose", "violet", "emerald", "cyan", "orange", "indigo"]

    should_alert, severity, message = alert_meta_for_detection(DetectionStatus.unknown, None, "Unknown")
    assert should_alert is True
    assert severity == "medium"


def test_hierarchical_search_integration():
    """Verify HierarchicalSearchEngine and its integration with Recognizer and TemporalTrackManager."""
    import numpy as np
    from facial_recognition.hierarchical_search import HierarchicalSearchEngine, SearchTier
    from facial_recognition.recognizer import Recognizer
    from facial_recognition.track_fusion import TemporalTrackManager, FaceObservation

    # Mock cloud search returning an enrolled cloud identity
    def mock_cloud_search(emb):
        return {
            "matches": [{"identity": "Alice Cloud", "score": 0.88, "profile_id": "prof_alice"}]
        }

    engine = HierarchicalSearchEngine(
        local_high_confidence_threshold=0.70,
        local_uncertain_threshold=0.35,
        cloud_recognition_threshold=0.50,
        cloud_search_fn=mock_cloud_search,
    )

    # Populate local gallery with Bob
    bob_emb = np.ones(512, dtype=np.float32)
    bob_emb /= np.linalg.norm(bob_emb)
    engine.gallery.update(labels=["Bob Local"], embeddings=bob_emb.reshape(1, -1), version=1)

    # 1. Query with exact Bob embedding -> should resolve locally
    res_bob = engine.search(bob_emb)
    assert res_bob.search_tier == SearchTier.LOCAL_HIGH_CONFIDENCE
    assert res_bob.identity == "Bob Local"
    assert res_bob.confidence > 0.99

    # 2. Query with orthogonal embedding -> should escalate to cloud and resolve Alice
    query_emb = np.zeros(512, dtype=np.float32)
    query_emb[0] = 1.0
    res_alice = engine.search(query_emb)
    assert res_alice.search_tier == SearchTier.CLOUD_RESOLVED
    assert res_alice.identity == "Alice Cloud"
    assert res_alice.confidence == 0.88

    # 3. Test Recognizer with hierarchical engine attached
    rec = Recognizer(gallery_path="", threshold=0.60, hierarchical_engine=engine)
    # Query with Alice's query_emb -> local gallery has only Bob, so rec.recognize escalates to engine
    ident, conf = rec.recognize(query_emb)
    assert ident == "Alice Cloud"
    assert conf == 0.88

    # 4. Test TemporalTrackManager with hierarchical engine
    track_mgr = TemporalTrackManager(
        min_observations_to_finalize=2,
        similarity_threshold=0.60,
        hierarchical_search_engine=engine,
    )
    obs1 = FaceObservation(timestamp=100.0, bbox=[10, 10, 50, 50], quality_score=90.0, quality_category="high", confidence=0.9, embedding=query_emb)
    obs2 = FaceObservation(timestamp=100.1, bbox=[11, 11, 51, 51], quality_score=90.0, quality_category="high", confidence=0.9, embedding=query_emb)
    
    # Process observations against empty local gallery
    pairs = track_mgr.process_frame_observations([obs1], [], np.zeros((0, 512), dtype=np.float32), current_time=100.0)
    assert len(pairs) == 1
    assert pairs[0][0].is_finalized is False  # Needs 2 obs

    pairs2 = track_mgr.process_frame_observations([obs2], [], np.zeros((0, 512), dtype=np.float32), current_time=100.1)
    assert len(pairs2) == 1
    # On 2nd observation, reached min_obs, local is unknown -> escalates to hierarchical engine -> Alice Cloud!
    assert pairs2[0][0].is_finalized is True
    assert pairs2[0][0].fused_identity == "Alice Cloud"


def test_landmark_face_alignment():
    """Verify 5-point landmark similarity transformation face alignment."""
    import numpy as np
    from facial_recognition.detector import align_face_crop, ARCFACE_REFERENCE_LANDMARKS_112

    # Synthetic test frame (200x200 RGB)
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[50:150, 50:150] = 200

    # 1. Test 5-point landmark alignment
    kps = np.array([
        [70, 80],   # left eye
        [130, 80],  # right eye
        [100, 110], # nose
        [80, 140],  # left mouth
        [120, 140]  # right mouth
    ], dtype=np.float32)

    aligned = align_face_crop(frame, bbox=[50, 50, 150, 150], kps=kps, target_size=(112, 112))
    assert aligned is not None
    assert aligned.shape == (112, 112, 3)

    # 2. Test fallback aspect-ratio preserving crop when kps is None
    fallback_aligned = align_face_crop(frame, bbox=[40, 60, 160, 180], kps=None, target_size=(112, 112))
    assert fallback_aligned is not None
    assert fallback_aligned.shape == (112, 112, 3)


def test_hnsw_index_definitions():
    """Verify HNSW vector indexes are defined in SQLAlchemy models with cosine distance ops."""
    from models import Embedding, Detection

    emb_idx_names = {idx.name: idx for idx in Embedding.__table__.indexes}
    assert "ix_embeddings_vector_hnsw" in emb_idx_names
    hnsw_emb = emb_idx_names["ix_embeddings_vector_hnsw"]
    assert hnsw_emb.dialect_options["postgresql"]["using"] == "hnsw"
    assert hnsw_emb.dialect_options["postgresql"]["ops"] == {"vector": "vector_cosine_ops"}

    det_idx_names = {idx.name: idx for idx in Detection.__table__.indexes}
    assert "ix_detections_embedding_vector_hnsw" in det_idx_names
    hnsw_det = det_idx_names["ix_detections_embedding_vector_hnsw"]
    assert hnsw_det.dialect_options["postgresql"]["using"] == "hnsw"
    assert hnsw_det.dialect_options["postgresql"]["ops"] == {"embedding_vector": "vector_cosine_ops"}


def test_face_anti_spoofing_liveness():
    """Verify multi-spectral Face Anti-Spoofing (FAS) assessment."""
    import numpy as np
    from facial_recognition.quality import FaceQualityAssessor

    assessor = FaceQualityAssessor()

    # 1. Natural synthetic face-like patch with color variance
    natural_patch = np.zeros((80, 80, 3), dtype=np.uint8)
    natural_patch[:, :, 0] = 120 # B
    natural_patch[:, :, 1] = 140 # G
    natural_patch[:, :, 2] = 190 # R (skin tone)
    # Add natural texture noise
    noise = np.random.randint(-15, 15, (80, 80, 3), dtype=np.int16)
    natural_patch = np.clip(natural_patch.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    score_natural = assessor.compute_liveness_score(natural_patch)
    assert 0.0 <= score_natural <= 1.0
    assert score_natural > 0.40

    # 2. Flat monochrome print (severe PAD penalty)
    flat_patch = np.ones((80, 80, 3), dtype=np.uint8) * 128
    score_flat = assessor.compute_liveness_score(flat_patch)
    assert score_flat < score_natural




