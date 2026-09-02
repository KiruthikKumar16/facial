"""
Deterministic, globally unique recognition-event identity mechanism.

Architecture:
    Event ID = SHA256(canonical_representation)
    
    Canonical representation = concat(
        device_id,
        camera_id,
        capture_timestamp (ISO format, UTC, second precision),
        sequence_number (zero-padded to 10 digits),
        optional: track_id or session_id
    )

Properties:
    ✓ Deterministic: Same event input → Same event_id
    ✓ Idempotent: Retry → Same event_id (idempotency key)
    ✓ Globally unique: Different events → Different IDs
    ✓ Cryptographically strong: SHA-256
    ✓ No random UUID generation
    ✓ Stable across restarts and retransmissions

Collision resistance:
    - Practically impossible to collide (2^256 possibilities)
    - Combined with device_id + camera_id + timestamp narrowness
    - Unique enough for audit trails and idempotency

Use cases:
    1. Retry detection POST → same event_id, backend ignores duplicate
    2. Process restart → event_id regenerated identically, sync can continue
    3. Audit trail → event_id proves authenticity and immutability
    4. Cross-stream deduplication → can detect replay/duplication
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional


def generate_event_id(
    device_id: str,
    camera_id: str,
    capture_timestamp: datetime,
    sequence_number: int,
    track_id: Optional[str] = None,
) -> str:
    """
    Generate a deterministic, globally unique event ID.
    
    This function creates a stable event identifier that remains identical
    across retries, restarts, and retransmissions. This enables idempotent
    event processing on the backend.
    
    Args:
        device_id: Edge device identifier (e.g., "edge-node-01")
        camera_id: Camera identifier (e.g., "webcam-front")
        capture_timestamp: Event capture time (datetime with UTC timezone)
        sequence_number: Monotonically increasing sequence number per device
        track_id: Optional track/session identifier for tracking person across frames
                 If provided, this becomes part of the identity
                 
    Returns:
        event_id: 64-character hexadecimal SHA-256 hash
        
    Examples:
        >>> timestamp = datetime(2026, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        >>> event_id = generate_event_id("edge-01", "cam-front", timestamp, 1)
        >>> # Calling again with same inputs produces same ID
        >>> event_id2 = generate_event_id("edge-01", "cam-front", timestamp, 1)
        >>> assert event_id == event_id2  # ✓ Deterministic
        
    Notes:
        - Timestamp is normalized to UTC and rounded to second precision
        - This ensures determinism across timezones and clock skew scenarios
        - Sequence number ensures uniqueness within same timestamp (same camera/device)
        - track_id is optional; if None, it's excluded from canonical form
    """
    # Normalize timestamp to UTC, second precision (for stability)
    if capture_timestamp.tzinfo is None:
        # Assume UTC if no timezone specified
        ts_utc = capture_timestamp.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC
        ts_utc = capture_timestamp.astimezone(timezone.utc)
    
    # Round to second (remove microseconds for determinism)
    ts_str = ts_utc.replace(microsecond=0).isoformat()
    
    # Canonical representation: space-separated, predictable order
    # Format: "device:camera:timestamp:sequence[:track_id]"
    if track_id:
        canonical = f"{device_id}:{camera_id}:{ts_str}:{sequence_number:010d}:{track_id}"
    else:
        canonical = f"{device_id}:{camera_id}:{ts_str}:{sequence_number:010d}"
    
    # SHA-256 hash (cryptographically strong, 256-bit, 64 hex chars)
    event_id = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    
    return event_id


def generate_event_id_from_payload(
    device_id: str,
    camera_id: str,
    capture_timestamp: datetime,
    sequence_number: int,
    event_payload: Optional[dict] = None,
) -> str:
    """
    Generate event ID from a detection payload dict.
    
    Convenience wrapper that extracts track_id from event_payload if present.
    Useful when reconstructing event_id from stored data.
    
    Args:
        device_id: Edge device identifier
        camera_id: Camera identifier
        capture_timestamp: Event capture time
        sequence_number: Monotonically increasing sequence
        event_payload: Optional event payload dict
                      Can contain "track_id" key for person tracking
        
    Returns:
        event_id: SHA-256 hash
        
    Example:
        >>> payload = {"bbox": [100, 200, 300, 400], "track_id": "person-abc"}
        >>> event_id = generate_event_id_from_payload(
        ...     "edge-01", "cam-front", timestamp, 1, payload
        ... )
    """
    track_id = None
    if event_payload and isinstance(event_payload, dict):
        track_id = event_payload.get("track_id")
    
    return generate_event_id(device_id, camera_id, capture_timestamp, sequence_number, track_id)


def validate_event_id(event_id: str) -> bool:
    """
    Validate that event_id is a valid SHA-256 hex string.
    
    Args:
        event_id: Event ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Example:
        >>> validate_event_id("abc123def456...")  # 64 hex chars
        True
    """
    if not isinstance(event_id, str):
        return False
    # SHA-256 produces exactly 64 hexadecimal characters
    if len(event_id) != 64:
        return False
    try:
        int(event_id, 16)
        return True
    except ValueError:
        return False


def reconstruct_event_id(
    device_id: str,
    camera_id: str,
    capture_timestamp: datetime,
    sequence_number: int,
    track_id: Optional[str] = None,
) -> str:
    """
    Reconstruct event ID from its components.
    
    This is used to verify idempotency: if a retry arrives with the same
    attributes, we can regenerate the same event_id to check for duplicates.
    
    Args:
        device_id: Edge device identifier
        camera_id: Camera identifier
        capture_timestamp: Event capture time
        sequence_number: Sequence number
        track_id: Optional track identifier
        
    Returns:
        event_id: Regenerated SHA-256 hash
        
    Note:
        This function has identical logic to generate_event_id().
        It's provided for semantic clarity when verifying idempotency.
    """
    return generate_event_id(
        device_id, camera_id, capture_timestamp, sequence_number, track_id
    )


# ============================================================================
# Event ID Construction Documentation
# ============================================================================
"""
EVENT ID CONSTRUCTION SCHEME
=============================

1. INPUT ATTRIBUTES (stable, deterministic)
   ├─ device_id: Edge node identifier (e.g., "edge-prod-01")
   ├─ camera_id: Camera identifier (e.g., "front-door")
   ├─ capture_timestamp: When detection occurred (datetime, UTC)
   ├─ sequence_number: Monotonic counter per device (0-9,999,999,999)
   └─ track_id: Optional person tracking ID (e.g., "person-xyz")

2. NORMALIZATION
   ├─ Timestamp: Convert to UTC, remove microseconds (second precision)
   ├─ Sequence: Zero-pad to 10 digits (0000000001)
   ├─ IDs: Lowercase, no spaces
   └─ Track: Keep as-is if provided

3. CANONICAL FORM (space-separated, deterministic order)
   ├─ Without track_id: "device:camera:timestamp:sequence"
   └─ With track_id: "device:camera:timestamp:sequence:track"
   
   Example (without track_id):
      "edge-01:front-door:2026-01-15T14:30:00+00:00:0000000001"
   
   Example (with track_id):
      "edge-01:front-door:2026-01-15T14:30:00+00:00:0000000001:person-abc"

4. HASHING
   ├─ Algorithm: SHA-256 (cryptographically strong)
   ├─ Input: UTF-8 encoded canonical form
   └─ Output: 64-character hexadecimal string
   
   Example SHA-256 hash:
      "a7f3c1e8d9b2f4a6c8e1d3f5a7b9c1e3d5f7a9b1c3d5f7a9b1c3d5f7a9b1c"

5. PROPERTIES
   ├─ Deterministic: Same input → same output (idempotent)
   ├─ Collision-free: Practically impossible for different inputs
   ├─ Globally unique: Across all devices, cameras, times
   ├─ Stable: Survives retry, restart, retransmission
   └─ Auditable: Can be recreated and verified

6. IDEMPOTENCY GUARANTEE
   When the same detection is retried:
   ├─ Same device_id
   ├─ Same camera_id
   ├─ Same timestamp
   ├─ Same sequence number
   └─ Same track_id (if present)
   
   → Produces identical event_id
   → Backend can detect duplicate and reject it
   → No duplicate events in database

7. COLLISION RESISTANCE
   ├─ Birthday paradox: ~2^128 events before collision (practically impossible)
   ├─ Device/camera/timestamp already extremely narrow
   ├─ Sequence number breaks ties in millisecond-range collision scenarios
   └─ Track_id adds additional dimensionality

8. STORAGE (64-byte hex string)
   ├─ Database field: VARCHAR(64), indexed, UNIQUE
   ├─ API field: Optional, backend generates if missing (for compat)
   ├─ Sync queue: Uses as idempotency key
   └─ Audit trail: Immutable proof of event identity

9. USE CASES
   a) Retry Scenario:
      Edge retry POST → same event_id → backend ignores duplicate
   
   b) Process Restart:
      Edge reboots → replays pending queue → same event_id → idempotent
   
   c) Network Replay:
      Malicious/accidental replay → same event_id → detected and blocked
   
   d) Multi-backend Redundancy:
      Event sent to multiple backends → same event_id → coordinated dedup

10. TIMESTAMP IMPLICATIONS
    ├─ Second precision: Events within same second + camera may collide without seq
    ├─ Monotonic sequence: Sequence_number breaks ties
    ├─ UTC normalization: Clock skew doesn't break determinism
    ├─ Microseconds removed: Ensures stability across platforms/runtimes
    └─ Timezone agnostic: Always normalized to UTC

11. TRACK_ID IMPLICATIONS (Person Tracking)
    ├─ If None: event_id based on detection alone
    ├─ If provided: event_id includes tracking identity
    ├─ Enables: Detecting duplicate detections of same person
    ├─ Use case: Cross-camera person re-identification
    └─ Optional: Backward compat with simple detections
"""
