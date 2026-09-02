import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
import pytest
import tempfile
import json
from unittest.mock import patch, MagicMock

from facial_recognition.event_ledger import EventLedger
from facial_recognition.logger import DetectionLogger, PriorityRuleEngine

@pytest.fixture
def temp_db_path(tmp_path):
    path = str(tmp_path / "ledger_test.db")
    yield path

def test_priority_rule_engine():
    assert PriorityRuleEngine.get_priority("Unknown", 0.5) == (25, "low")
    assert PriorityRuleEngine.get_priority("Alice", 0.8) == (50, "normal")
    assert PriorityRuleEngine.get_priority("Bob", 0.95) == (75, "high")
    assert PriorityRuleEngine.get_priority("Eve", 0.99, role="blacklist") == (100, "critical")

def test_event_ledger_priority_ordering(temp_db_path):
    ledger = EventLedger(db_path=temp_db_path)
    
    # Add events out of priority order
    ledger.add_event("cam-1", identity="LowConf", confidence=0.5, priority=25)
    ledger.add_event("cam-1", identity="HighConf", confidence=0.95, priority=75)
    ledger.add_event("cam-1", identity="Critical", confidence=0.99, priority=100)
    ledger.add_event("cam-1", identity="Normal", confidence=0.8, priority=50)
    
    pending = ledger.get_pending_events()
    
    # Should be sorted by priority DESC
    assert len(pending) == 4
    assert pending[0]["identity"] == "Critical"
    assert pending[1]["identity"] == "HighConf"
    assert pending[2]["identity"] == "Normal"
    assert pending[3]["identity"] == "LowConf"

def test_starvation_prevention(temp_db_path):
    ledger = EventLedger(db_path=temp_db_path)
    
    # Add a low priority event
    ledger.add_event("cam-1", identity="LowConf", confidence=0.5, priority=25)
    
    # Manually backdate the created_at in sync_queue to simulate waiting
    conn = ledger._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sync_queue SET created_at = ?", ((datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat(),))
    conn.commit()
    
    # Prevent starvation (boost by 25)
    boosted = ledger.prevent_starvation(max_wait_seconds=300, boost_amount=25)
    assert boosted == 1
    
    pending = ledger.get_pending_events()
    assert pending[0]["queue_priority"] == 50  # 25 + 25

def test_logger_queue_metrics(temp_db_path):
    ledger = EventLedger(db_path=temp_db_path)
    ledger.add_event("cam-1", priority=100)
    ledger.add_event("cam-1", priority=100)
    ledger.add_event("cam-1", priority=50)
    
    stats = ledger.get_stats()
    assert stats["priority_queue"] == {100: 2, 50: 1}
