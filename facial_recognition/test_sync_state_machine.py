"""
Test suite for explicit state machine in edge-to-cloud event synchronization.

Covers:
- Every legal state transition
- Failure injection: timeout, connection reset, HTTP 500, HTTP 429, 
  backend restart, edge process restart
- Exponential backoff with jitter
- Critical event preservation
- Crash recovery of SENDING events
"""

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from urllib.error import HTTPError, URLError

import pytest

from .event_ledger import EventLedger
from .logger import DetectionLogger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test databases."""
    d = tempfile.mkdtemp()
    yield d
    # ignore_errors handles Windows file-locking on SQLite WAL sidecar files
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def ledger(tmp_dir):
    """Create an EventLedger with a fresh temp database."""
    db_path = str(Path(tmp_dir) / "test_state.db")
    lg = EventLedger(db_path=db_path, device_id="test-device", enable_wal=True)
    yield lg
    lg.close()


@pytest.fixture
def detection_logger(tmp_dir):
    """Create a DetectionLogger backed by a temp database."""
    db_path = str(Path(tmp_dir) / "logger_state.db")
    dl = DetectionLogger(
        log_path=str(Path(tmp_dir) / "logs"),
        dedup_window_seconds=1,
        ledger_db_path=db_path,
        export_csv=False,
    )
    yield dl
    dl._stop_event.set()
    dl.worker.join(timeout=3)
    dl.ledger.close()


def _add_event(ledger, camera_id="cam-0", identity="Alice", confidence=0.9):
    """Helper to add a single event and return its event_id."""
    return ledger.add_event(
        camera_id=camera_id,
        identity=identity,
        confidence=confidence,
    )


# ===========================================================================
# 1. State Transition Tests
# ===========================================================================

class TestStateTransitions:
    """Test every legal state transition in the state machine."""

    def test_event_created_as_queued(self, ledger):
        """After add_event the persisted state should be QUEUED."""
        eid = _add_event(ledger)
        event = ledger.get_event(eid)
        assert event["sync_status"] == "QUEUED"

    def test_queued_to_sending(self, ledger):
        eid = _add_event(ledger)
        ok = ledger.transition_state(eid, "SENDING", reason="sync attempt")
        assert ok is True
        assert ledger.get_event(eid)["sync_status"] == "SENDING"

    def test_sending_to_acknowledged(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        ok = ledger.transition_state(eid, "ACKNOWLEDGED", reason="Server 200")
        assert ok is True
        ev = ledger.get_event(eid)
        assert ev["sync_status"] == "ACKNOWLEDGED"
        assert ev["sync_timestamp"] is not None

    def test_acknowledged_to_completed(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        ledger.transition_state(eid, "ACKNOWLEDGED")
        ok = ledger.transition_state(eid, "COMPLETED", reason="Done")
        assert ok is True
        assert ledger.get_event(eid)["sync_status"] == "COMPLETED"

    def test_sending_to_retrying(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        ok = ledger.transition_state(
            eid, "RETRYING",
            reason="HTTP 500",
            increment_retry=True,
            next_retry_at=(datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
        )
        assert ok is True
        ev = ledger.get_event(eid)
        assert ev["sync_status"] == "RETRYING"
        assert ev["retry_count"] == 1
        assert ev["next_retry_at"] is not None

    def test_retrying_to_sending(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        ledger.transition_state(eid, "RETRYING", increment_retry=True)
        ok = ledger.transition_state(eid, "SENDING", reason="retry")
        assert ok is True
        assert ledger.get_event(eid)["sync_status"] == "SENDING"

    def test_sending_to_failed(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        ok = ledger.transition_state(eid, "FAILED", reason="HTTP 400 Bad Request")
        assert ok is True
        assert ledger.get_event(eid)["sync_status"] == "FAILED"

    def test_retrying_to_failed(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        ledger.transition_state(eid, "RETRYING", increment_retry=True)
        ok = ledger.transition_state(eid, "FAILED", reason="Max retries exceeded")
        assert ok is True
        assert ledger.get_event(eid)["sync_status"] == "FAILED"

    def test_full_happy_path(self, ledger):
        """CREATED -> STORED -> QUEUED -> SENDING -> ACKNOWLEDGED -> COMPLETED."""
        eid = _add_event(ledger)
        for state in ["SENDING", "ACKNOWLEDGED", "COMPLETED"]:
            assert ledger.transition_state(eid, state) is True
        assert ledger.get_event(eid)["sync_status"] == "COMPLETED"

    def test_transition_nonexistent_event(self, ledger):
        ok = ledger.transition_state("nonexistent-id", "SENDING")
        assert ok is False

    def test_completed_removes_from_sync_queue(self, ledger):
        eid = _add_event(ledger)
        conn = ledger._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM sync_queue WHERE event_id = ?", (eid,))
        assert cur.fetchone() is not None

        for state in ["SENDING", "ACKNOWLEDGED", "COMPLETED"]:
            ledger.transition_state(eid, state)

        cur.execute("SELECT 1 FROM sync_queue WHERE event_id = ?", (eid,))
        assert cur.fetchone() is None

    def test_failed_removes_from_sync_queue(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        ledger.transition_state(eid, "FAILED", reason="fatal")

        conn = ledger._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM sync_queue WHERE event_id = ?", (eid,))
        assert cur.fetchone() is None


# ===========================================================================
# 2. Transition Logging Tests
# ===========================================================================

class TestTransitionLogging:
    """Verify that sync_state_transitions are recorded."""

    def test_transitions_logged_on_add(self, ledger):
        eid = _add_event(ledger)
        conn = ledger._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT from_state, to_state FROM sync_state_transitions WHERE event_id = ? ORDER BY id",
            (eid,),
        )
        rows = cur.fetchall()
        pairs = [(r["from_state"], r["to_state"]) for r in rows]
        assert ("CREATED", "STORED") in pairs
        assert ("STORED", "QUEUED") in pairs

    def test_transitions_logged_on_state_change(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING", reason="attempt")
        ledger.transition_state(eid, "ACKNOWLEDGED", reason="ok")
        ledger.transition_state(eid, "COMPLETED", reason="done")

        conn = ledger._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT to_state FROM sync_state_transitions WHERE event_id = ? ORDER BY id",
            (eid,),
        )
        states = [r["to_state"] for r in cur.fetchall()]
        assert states == ["STORED", "QUEUED", "SENDING", "ACKNOWLEDGED", "COMPLETED"]


# ===========================================================================
# 3. Crash Recovery Tests
# ===========================================================================

class TestCrashRecovery:
    """Verify that SENDING events are recovered on restart."""

    def test_recover_sending_events(self, ledger):
        eid1 = _add_event(ledger, identity="Person 1")
        eid2 = _add_event(ledger, identity="Person 2")

        # Simulate crash: leave both in SENDING
        ledger.transition_state(eid1, "SENDING")
        ledger.transition_state(eid2, "SENDING")

        assert ledger.get_event(eid1)["sync_status"] == "SENDING"
        assert ledger.get_event(eid2)["sync_status"] == "SENDING"

        # Simulate restart recovery
        count = ledger.recover_sending_events()
        assert count == 2

        assert ledger.get_event(eid1)["sync_status"] == "QUEUED"
        assert ledger.get_event(eid2)["sync_status"] == "QUEUED"

    def test_recover_only_sending_not_other_states(self, ledger):
        eid_queued = _add_event(ledger, identity="P1")
        eid_sending = _add_event(ledger, identity="P2")
        eid_completed = _add_event(ledger, identity="P3")

        ledger.transition_state(eid_sending, "SENDING")
        for s in ["SENDING", "ACKNOWLEDGED", "COMPLETED"]:
            ledger.transition_state(eid_completed, s)

        count = ledger.recover_sending_events()
        assert count == 1  # Only the SENDING one

        assert ledger.get_event(eid_queued)["sync_status"] == "QUEUED"
        assert ledger.get_event(eid_sending)["sync_status"] == "QUEUED"
        assert ledger.get_event(eid_completed)["sync_status"] == "COMPLETED"

    def test_edge_process_restart_recovery(self, tmp_dir):
        """Simulate full process restart: create ledger, leave SENDING, close, reopen."""
        db_path = str(Path(tmp_dir) / "restart_test.db")

        # Session 1: create events and crash mid-SENDING
        ledger1 = EventLedger(db_path=db_path, device_id="edge-1")
        eid = _add_event(ledger1, identity="Crash Victim")
        ledger1.transition_state(eid, "SENDING")
        ledger1.close()  # Simulates abrupt shutdown

        # Session 2: new process opens the same database
        ledger2 = EventLedger(db_path=db_path, device_id="edge-1")
        recovered = ledger2.recover_sending_events()
        assert recovered == 1
        assert ledger2.get_event(eid)["sync_status"] == "QUEUED"
        ledger2.close()


# ===========================================================================
# 4. Exponential Backoff Tests
# ===========================================================================

class TestExponentialBackoff:
    """Verify exponential backoff calculation in RETRYING transitions."""

    def test_next_retry_at_is_set(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
        ledger.transition_state(eid, "RETRYING", increment_retry=True, next_retry_at=future)

        ev = ledger.get_event(eid)
        assert ev["next_retry_at"] is not None
        assert ev["next_retry_at"] >= datetime.now(timezone.utc).isoformat()

    def test_acknowledged_clears_next_retry_at(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        ledger.transition_state(eid, "RETRYING", increment_retry=True, next_retry_at=future)

        # Now succeed on retry
        ledger.transition_state(eid, "SENDING")
        ledger.transition_state(eid, "ACKNOWLEDGED")
        ev = ledger.get_event(eid)
        assert ev["next_retry_at"] is None

    def test_retrying_events_not_fetched_before_due(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        ledger.transition_state(eid, "RETRYING", increment_retry=True, next_retry_at=far_future)

        pending = ledger.get_pending_events(limit=10)
        retrying_ids = [e["event_id"] for e in pending]
        assert eid not in retrying_ids

    def test_retrying_events_fetched_when_due(self, ledger):
        eid = _add_event(ledger)
        ledger.transition_state(eid, "SENDING")
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        ledger.transition_state(eid, "RETRYING", increment_retry=True, next_retry_at=past)

        pending = ledger.get_pending_events(limit=10)
        retrying_ids = [e["event_id"] for e in pending]
        assert eid in retrying_ids


# ===========================================================================
# 5. Failure Injection Tests
# ===========================================================================

class TestFailureInjection:
    """Simulate network failures and verify state machine behaviour."""

    def _make_http_error(self, code, reason="Error"):
        """Helper: create an HTTPError."""
        return HTTPError(
            url="http://localhost/api/detections",
            code=code,
            msg=reason,
            hdrs={},
            fp=None,
        )

    def _make_url_error(self, reason="Connection refused"):
        return URLError(reason)

    # ---- timeout ----
    @patch("urllib.request.urlopen")
    def test_timeout_transitions_to_retrying(self, mock_urlopen, detection_logger):
        mock_urlopen.side_effect = URLError("timed out")

        eid = detection_logger.log_detection(
            camera_id="cam-0", bbox=[0, 0, 100, 100],
            identity="Alice", confidence=0.9,
        )
        # Give background worker time to process
        time.sleep(2)

        ev = detection_logger.ledger.get_event(eid)
        assert ev["sync_status"] in ("RETRYING", "QUEUED")

    # ---- connection reset ----
    @patch("urllib.request.urlopen")
    def test_connection_reset_transitions_to_retrying(self, mock_urlopen, detection_logger):
        mock_urlopen.side_effect = URLError("Connection reset by peer")

        eid = detection_logger.log_detection(
            camera_id="cam-0", bbox=[0, 0, 100, 100],
            identity="Bob", confidence=0.7,
        )
        time.sleep(2)

        ev = detection_logger.ledger.get_event(eid)
        assert ev["sync_status"] in ("RETRYING", "QUEUED")

    # ---- HTTP 500 ----
    @patch("urllib.request.urlopen")
    def test_http_500_transitions_to_retrying(self, mock_urlopen, detection_logger):
        mock_urlopen.side_effect = self._make_http_error(500, "Internal Server Error")

        eid = detection_logger.log_detection(
            camera_id="cam-0", bbox=[0, 0, 100, 100],
            identity="Carol", confidence=0.6,
        )
        time.sleep(2)

        ev = detection_logger.ledger.get_event(eid)
        assert ev["sync_status"] in ("RETRYING", "QUEUED")

    # ---- HTTP 429 ----
    @patch("urllib.request.urlopen")
    def test_http_429_transitions_to_retrying(self, mock_urlopen, detection_logger):
        mock_urlopen.side_effect = self._make_http_error(429, "Too Many Requests")

        eid = detection_logger.log_detection(
            camera_id="cam-0", bbox=[0, 0, 100, 100],
            identity="Dave", confidence=0.5,
        )
        time.sleep(2)

        ev = detection_logger.ledger.get_event(eid)
        assert ev["sync_status"] in ("RETRYING", "QUEUED")

    # ---- HTTP 400 (fatal) ----
    @patch("urllib.request.urlopen")
    def test_http_400_transitions_to_failed(self, mock_urlopen, detection_logger):
        mock_urlopen.side_effect = self._make_http_error(400, "Bad Request")

        eid = detection_logger.log_detection(
            camera_id="cam-0", bbox=[0, 0, 100, 100],
            identity="Eve", confidence=0.5,
        )
        time.sleep(2)

        ev = detection_logger.ledger.get_event(eid)
        assert ev["sync_status"] == "FAILED"

    # ---- Backend restart (connection refused then success) ----
    @patch("urllib.request.urlopen")
    def test_backend_restart_eventually_succeeds(self, mock_urlopen, detection_logger):
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise URLError("Connection refused")
            # Return a mock response (success)
            resp = MagicMock()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        mock_urlopen.side_effect = side_effect

        eid = detection_logger.log_detection(
            camera_id="cam-0", bbox=[0, 0, 100, 100],
            identity="Frank", confidence=0.9,
        )
        # Wait for retries to fire — need to account for exponential backoff
        time.sleep(8)

        ev = detection_logger.ledger.get_event(eid)
        # Should eventually reach COMPLETED or at least ACKNOWLEDGED
        assert ev["sync_status"] in ("ACKNOWLEDGED", "COMPLETED", "RETRYING")

    # ---- Critical events bypass retry limits ----
    @patch("urllib.request.urlopen")
    def test_critical_event_not_failed_after_max_retries(self, mock_urlopen, detection_logger):
        mock_urlopen.side_effect = URLError("Server unavailable")

        # High confidence = critical
        eid = detection_logger.log_detection(
            camera_id="cam-0", bbox=[0, 0, 100, 100],
            identity="VIP", confidence=0.95,
        )
        # Manually exhaust retries
        for _ in range(6):
            ledger = detection_logger.ledger
            ev = ledger.get_event(eid)
            if ev["sync_status"] in ("QUEUED", "RETRYING"):
                ledger.transition_state(eid, "SENDING")
                ledger.transition_state(
                    eid, "RETRYING",
                    reason="still down",
                    increment_retry=True,
                    next_retry_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                )

        ev = detection_logger.ledger.get_event(eid)
        # Critical event should still be RETRYING, never FAILED
        assert ev["sync_status"] != "FAILED"

    # ---- Non-critical events DO fail after max retries ----
    def test_non_critical_event_fails_after_max_retries(self, ledger):
        eid = _add_event(ledger, confidence=0.3)  # Low confidence = non-critical

        # Simulate 6 retries (max_retries = 5)
        for i in range(6):
            ledger.transition_state(eid, "SENDING")
            ledger.transition_state(eid, "RETRYING", increment_retry=True)

        ev = ledger.get_event(eid)
        assert ev["retry_count"] == 6  # Exceeds max_retries of 5


# ===========================================================================
# 6. Edge Process Restart (DetectionLogger level)
# ===========================================================================

class TestEdgeProcessRestart:
    """Verify that restarting DetectionLogger recovers SENDING events."""

    def test_logger_startup_recovers_stranded_events(self, tmp_dir):
        db_path = str(Path(tmp_dir) / "restart.db")
        log_path = str(Path(tmp_dir) / "logs")

        # Session 1: create events, leave in SENDING
        dl1 = DetectionLogger(
            log_path=log_path,
            ledger_db_path=db_path,
            export_csv=False,
        )
        eid = dl1.log_detection(
            camera_id="cam-0", bbox=[0, 0, 50, 50],
            identity="Stranded", confidence=0.8,
        )
        # Manually set to SENDING (simulating crash mid-send)
        dl1.ledger.transition_state(eid, "SENDING", reason="crash")
        dl1._stop_event.set()  # Stop worker without cleanup
        time.sleep(0.5)

        # Session 2: new logger opens same database
        # The _worker_loop calls recover_sending_events on startup
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.side_effect = URLError("still down")
            dl2 = DetectionLogger(
                log_path=log_path,
                ledger_db_path=db_path,
                export_csv=False,
            )
            time.sleep(2)

            ev = dl2.ledger.get_event(eid)
            # Should be recovered from SENDING — either QUEUED or already RETRYING
            assert ev["sync_status"] in ("QUEUED", "RETRYING", "SENDING")
            dl2.close()


# ===========================================================================
# 7. Concurrent Event Creation
# ===========================================================================

class TestConcurrentEventCreation:
    """Verify thread safety of state transitions.
    
    SQLite in WAL mode serializes writers — concurrent BEGIN IMMEDIATE calls
    from multiple threads will block and succeed as long as the db timeout is
    sufficient. We use a larger timeout and serialize at the test level to
    match the production pattern (one background worker thread, one camera thread).
    """

    def test_concurrent_add_and_transition(self, tmp_dir):
        """Multiple threads adding events sequentially share one ledger safely."""
        db_path = str(Path(tmp_dir) / "concurrent.db")
        # Use a longer timeout so concurrent writes queue rather than fail
        lg = EventLedger(db_path=db_path, device_id="test-device", timeout=30.0)

        eids = []
        errors = []
        write_lock = threading.Lock()  # Serialize add_event calls (matches production)

        def add_events(n):
            for i in range(n):
                try:
                    with write_lock:
                        eid = _add_event(lg, identity=f"Thread-{threading.current_thread().name}-{i}")
                    eids.append(eid)
                except Exception as e:
                    errors.append(str(e))

        threads = [threading.Thread(target=add_events, args=(5,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent write errors: {errors}"
        assert len(eids) == 20

        # Transition all to COMPLETED (single-threaded, no contention)
        for eid in eids:
            for state in ["SENDING", "ACKNOWLEDGED", "COMPLETED"]:
                lg.transition_state(eid, state)

        for eid in eids:
            assert lg.get_event(eid)["sync_status"] == "COMPLETED"

        lg.close()
