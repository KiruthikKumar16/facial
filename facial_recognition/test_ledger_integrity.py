import pytest
import os
import sqlite3
import tempfile
import json
from facial_recognition.event_ledger import EventLedger

@pytest.fixture
def ledger_and_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    ledger = EventLedger(db_path=path)
    yield ledger, path
    ledger.close()
    try:
        os.remove(path)
    except PermissionError:
        pass  # best-effort cleanup on Windows

def test_ledger_integrity_valid_chain(ledger_and_path):
    ledger, _ = ledger_and_path
    
    ledger.add_event("cam-1", identity="Alice", confidence=0.9)
    ledger.add_event("cam-1", identity="Bob", confidence=0.8)
    ledger.add_event("cam-1", identity="Charlie", confidence=0.95)
    
    result = ledger.verify_ledger_integrity("cam-1")
    assert result["is_valid"] is True
    assert result["events_verified"] == 3
    assert result["error"] is None

def test_ledger_integrity_tamper_payload(ledger_and_path):
    ledger, _ = ledger_and_path
    ledger.add_event("cam-1", identity="Alice", confidence=0.9)
    
    # Intentionally tamper: change confidence without recomputing hash
    conn = ledger._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE recognition_events SET confidence = 0.99 WHERE identity = 'Alice'")
    conn.commit()
    
    result = ledger.verify_ledger_integrity("cam-1")
    assert result["is_valid"] is False
    assert "Data tampered" in result["error"]

def test_ledger_integrity_tamper_event_hash(ledger_and_path):
    ledger, _ = ledger_and_path
    ledger.add_event("cam-1", identity="Alice", confidence=0.9)
    
    # Intentionally tamper the stored hash itself
    conn = ledger._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE recognition_events SET event_hash = 'deadbeef' WHERE identity = 'Alice'")
    conn.commit()
    
    result = ledger.verify_ledger_integrity("cam-1")
    assert result["is_valid"] is False
    assert "Data tampered" in result["error"]

def test_ledger_integrity_tamper_previous_hash(ledger_and_path):
    ledger, _ = ledger_and_path
    ledger.add_event("cam-1", identity="Alice", confidence=0.9)
    ledger.add_event("cam-1", identity="Bob", confidence=0.8)
    
    # Break the chain link on the second event
    conn = ledger._get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE recognition_events SET previous_event_hash = 'tampered' WHERE identity = 'Bob'")
    conn.commit()
    
    result = ledger.verify_ledger_integrity("cam-1")
    assert result["is_valid"] is False
    assert "Chain broken" in result["error"]

def test_ledger_integrity_tamper_order(ledger_and_path):
    ledger, _ = ledger_and_path
    ledger.add_event("cam-1", identity="Alice", confidence=0.9)
    ledger.add_event("cam-1", identity="Bob", confidence=0.8)
    
    # Swap sequence numbers to reorder events
    conn = ledger._get_connection()
    cursor = conn.cursor()
    seq_alice = cursor.execute("SELECT sequence_number FROM recognition_events WHERE identity='Alice'").fetchone()[0]
    seq_bob   = cursor.execute("SELECT sequence_number FROM recognition_events WHERE identity='Bob'").fetchone()[0]
    cursor.execute("UPDATE recognition_events SET sequence_number = -1 WHERE identity = 'Alice'")
    cursor.execute("UPDATE recognition_events SET sequence_number = ? WHERE identity = 'Bob'", (seq_alice,))
    cursor.execute("UPDATE recognition_events SET sequence_number = ? WHERE identity = 'Alice'", (seq_bob,))
    conn.commit()
    
    result = ledger.verify_ledger_integrity("cam-1")
    assert result["is_valid"] is False

def test_ledger_integrity_empty_camera(ledger_and_path):
    ledger, _ = ledger_and_path
    result = ledger.verify_ledger_integrity("nonexistent-cam")
    assert result["is_valid"] is True
    assert result["events_verified"] == 0
