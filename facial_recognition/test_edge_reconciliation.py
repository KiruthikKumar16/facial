import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import json

from facial_recognition.event_ledger import EventLedger

@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_reconciliation.db")
        yield db_path

@pytest.fixture
def ledger(temp_db):
    ledger = EventLedger(db_path=temp_db, device_id="test-edge-1")
    yield ledger
    ledger.close()

def test_get_sync_metadata_empty(ledger):
    """Test getting sync metadata when there are no events."""
    metadata = ledger.get_sync_metadata()
    assert metadata == []

def test_get_sync_metadata_with_events(ledger):
    """Test getting sync metadata calculates correct boundaries."""
    # Add events for cam-1
    # 1 -> COMPLETED
    ev1 = ledger.add_event("cam-1", "Person A", 0.9)
    ledger.transition_state(ev1, "QUEUED")
    ledger.transition_state(ev1, "SENDING")
    ledger.transition_state(ev1, "ACKNOWLEDGED")
    ledger.transition_state(ev1, "COMPLETED")
    
    # 2 -> COMPLETED
    ev2 = ledger.add_event("cam-1", "Person B", 0.9)
    ledger.transition_state(ev2, "QUEUED")
    ledger.transition_state(ev2, "SENDING")
    ledger.transition_state(ev2, "ACKNOWLEDGED")
    ledger.transition_state(ev2, "COMPLETED")

    # 3 -> QUEUED (lowest pending)
    ev3 = ledger.add_event("cam-1", "Person C", 0.9)
    ledger.transition_state(ev3, "QUEUED")
    
    # 4 -> FAILED (not pending sync, but part of sequence)
    ev4 = ledger.add_event("cam-1", "Person D", 0.9)
    ledger.transition_state(ev4, "QUEUED")
    ledger.transition_state(ev4, "FAILED")
    
    # 5 -> RETRYING
    ev5 = ledger.add_event("cam-1", "Person E", 0.9)
    ledger.transition_state(ev5, "QUEUED")
    ledger.transition_state(ev5, "RETRYING")
    
    # Add event for cam-2
    ev6 = ledger.add_event("cam-2", "Person F", 0.9)
    ledger.transition_state(ev6, "QUEUED")
    
    metadata = ledger.get_sync_metadata()
    assert len(metadata) == 2
    
    # Find cam-1 metadata
    cam1_meta = next(m for m in metadata if m["camera_id"] == "cam-1")
    assert cam1_meta["highest_local_sequence"] == 5
    assert cam1_meta["lowest_pending_sequence"] == 3
    assert cam1_meta["last_completed_sequence"] == 2
    
    # Find cam-2 metadata
    cam2_meta = next(m for m in metadata if m["camera_id"] == "cam-2")
    assert cam2_meta["highest_local_sequence"] == 1
    assert cam2_meta["lowest_pending_sequence"] == 1
    assert cam2_meta["last_completed_sequence"] is None

def test_requeue_sequence_ranges(ledger):
    """Test that missing sequence ranges are successfully requeued."""
    # Add 5 events
    events = []
    for i in range(1, 6):
        ev = ledger.add_event("cam-1", f"Person {i}", 0.9)
        events.append(ev)
        
    # Mark them all as COMPLETED initially
    for ev in events:
        ledger.transition_state(ev, "QUEUED")
        ledger.transition_state(ev, "SENDING")
        ledger.transition_state(ev, "ACKNOWLEDGED")
        ledger.transition_state(ev, "COMPLETED")
        
    # Backend says it's missing sequences 2, 3, and 5
    # Ranges: [2, 3], [5, 5]
    missing_ranges = [[2, 3], [5, 5]]
    
    requeued_count = ledger.requeue_sequence_ranges("cam-1", missing_ranges)
    assert requeued_count == 3
    
    # Verify states
    assert ledger.get_event(events[0])["sync_status"] == "COMPLETED"
    assert ledger.get_event(events[1])["sync_status"] == "QUEUED"
    assert ledger.get_event(events[2])["sync_status"] == "QUEUED"
    assert ledger.get_event(events[3])["sync_status"] == "COMPLETED"
    assert ledger.get_event(events[4])["sync_status"] == "QUEUED"
    
    # Verify retry counters were reset
    assert ledger.get_event(events[1])["retry_count"] == 0
    assert ledger.get_event(events[1])["next_retry_at"] is None
    
    # Verify they appear in the sync queue with high priority
    pending = ledger.get_pending_events(limit=10)
    assert len(pending) == 3
