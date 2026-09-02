# Integrity Model — Local Event Ledger

## Overview

The recognition event ledger maintains a cryptographically linked chain of events per camera. Every stored event carries two integrity fields:

| Field | Description |
|---|---|
| `event_hash` | SHA-256 hash of this event's canonical payload + previous hash |
| `previous_event_hash` | The `event_hash` of the immediately preceding event for the same camera |

The first event in any camera chain anchors to a **genesis hash** — 64 zero hex digits — as its `previous_event_hash`.

---

## Canonical Serialization

Before hashing, each event is serialized into a **deterministic canonical form** using `json.dumps(..., sort_keys=True)`. The following fields are included in the hash input:

```json
{
  "age": null,
  "camera_id": "cam-01",
  "capture_timestamp": "2026-09-01T09:00:00+00:00",
  "confidence": 0.950000,
  "device_id": "edge-device-hostname",
  "event_id": "sha256-deterministic-event-id",
  "event_payload": "{...}",
  "gender": null,
  "identity": "Alice",
  "previous_event_hash": "0000...0000",
  "sequence_number": 1
}
```

- All keys are lexicographically sorted.
- Floating-point confidence is rounded to 6 decimal places for stability.
- The `previous_event_hash` is included **inside** the hash input so that any chain-level tampering invalidates the current event's hash.

---

## Tamper DETECTION (What This System Does)

The system provides **detection**, not prevention. The `verify_ledger_integrity(camera_id)` method walks the full chain in `sequence_number` order and:

1. **Recalculates every event's hash** from first principles using the stored fields.
2. **Checks that `previous_event_hash` matches** the stored `event_hash` of the preceding record.

Any of the following tampering attacks are **detected**:

| Attack | Detection Method |
|---|---|
| Modify a field (e.g. `confidence`, `identity`) | Recalculated hash diverges from stored `event_hash` |
| Replace the `event_hash` with a fake value | Recalculated hash still diverges (cannot fake without re-hashing the full chain) |
| Break a `previous_event_hash` link | Chain continuity check fails |
| Reorder events (swap `sequence_number`) | Chain breaks at the out-of-order position |
| Insert a new event | Its `previous_event_hash` would not match the genuine chain position |
| Delete a middle event | The next event's `previous_event_hash` references a missing link |

---

## Tamper PREVENTION (What This System Does NOT Do)

> [!CAUTION]
> This system is **not a prevention mechanism**. An attacker with direct SQLite write access and knowledge of the hash algorithm could:
> - Modify event data **and** recompute the entire chain from that point forward.
> - Wipe all events and rebuild a fraudulent chain.

The integrity protection is meaningful under the following conditions:
- The ledger file is read-only to untrusted processes (OS-level file permissions).
- The verification is performed by a trusted party on a trusted copy of the database (e.g. after export or cloud upload).
- The **cloud-side** acknowledged sequence numbers act as an external reference. A chain that doesn't match cloud acknowledgements is a red flag.

---

## Schema

```sql
ALTER TABLE recognition_events ADD COLUMN event_hash          TEXT NOT NULL;
ALTER TABLE recognition_events ADD COLUMN previous_event_hash TEXT NOT NULL;
```

Existing events migrated from earlier schema versions receive the sentinel value `LEGACY_UNHASHED` and are skipped during verification.

---

## Using the Verification API

```python
from facial_recognition.event_ledger import EventLedger

ledger = EventLedger(db_path="facial_recognition.db")
result = ledger.verify_ledger_integrity("cam-01")

print(result)
# {
#   "is_valid": True,
#   "events_verified": 142,
#   "error": None,
#   "failed_sequence": None
# }
```

On failure:
```python
# {
#   "is_valid": False,
#   "events_verified": 7,
#   "error": "Data tampered: Calculated hash abc123... does not match stored def456...",
#   "failed_sequence": 8
# }
```

---

## Limitations Summary

| Limitation | Notes |
|---|---|
| Detection only, not prevention | Root-level attacker can rebuild chain |
| Per-camera chains only | Cross-camera ordering is not covered |
| No external anchor | Without an external witness (cloud ACK), a fully reconstructed chain is undetectable |
| Legacy rows not verified | Pre-migration events carry `LEGACY_UNHASHED` sentinel |
| Confidence rounding | Stored float must round to 6 decimal places consistently |
