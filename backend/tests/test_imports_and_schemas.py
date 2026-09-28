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
