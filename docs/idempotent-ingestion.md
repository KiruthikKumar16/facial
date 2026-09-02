# Idempotent Ingestion API

The backend ingestion API (`POST /api/detections`) guarantees exactly-once database effect through idempotent ingestion combined with at-least-once delivery from edge devices.

## Architecture

Edge devices implement an explicit state machine for synchronization. If the edge device fails to receive a HTTP `2xx` response (due to network timeout, HTTP 500, rate limiting, or connection reset), it will retry sending the same payload using exponential backoff. 

Because the edge device might retry a request that the server actually processed (but the response was lost in transit), the server must ensure that re-processing the same request does not result in duplicate records.

## Database Idempotency (`event_id`)

Every ingestion request requires an `event_id`, which is a deterministic SHA-256 hash generated at the edge node based on the detection properties.

The database schema enforces uniqueness on this column:
```sql
ALTER TABLE detections ADD CONSTRAINT uq_detections_event_id UNIQUE (event_id);
```

The backend inserts the detection atomically. If the insertion fails due to an `IntegrityError` (a duplicate `event_id`), the backend catches it, rolls back the insertion, fetches the existing row, and returns it. 

### Why Database-Level Enforcement?

Previously, the backend used a Python-level `SELECT` before the `INSERT`. This created a race condition:

1. Thread A checks if `event_id=123` exists. (False)
2. Thread B checks if `event_id=123` exists. (False)
3. Thread A inserts `event_id=123`.
4. Thread B inserts `event_id=123`. -> Duplicate or Error!

By catching `IntegrityError` (which under the hood leverages index locking or `ON CONFLICT` semantics depending on the dialect), the duplication is handled atomically and lock-free across all database clients, completely closing the race condition.

## The `inserted` Flag

The API response includes an `inserted` boolean field:
- `inserted: true` — The backend successfully wrote a new record to the database.
- `inserted: false` — The record already existed. The backend safely ignored the duplicate and returned the existing row.

This deterministic outcome allows edge nodes to safely retry any `SENDING` event indefinitely without fear of corrupting the cloud database state.

## Production Note

For existing deployments, you must manually run the database migration or add the unique index to the PostgreSQL database if Alembic did not already create it:

```sql
CREATE UNIQUE INDEX CONCURRENTLY uq_detections_event_id ON detections(event_id);
```
