# Recognition-Event Provenance Tracking Architecture

## 1. Executive Summary
In safety-critical and enterprise biometric deployments, recognition decisions must be transparent, verifiable, and legally auditable. The **Recognition-Event Provenance Tracking System** captures an immutable, 7-stage lineage graph for every facial recognition decision:

$$\text{Camera} \longrightarrow \text{Frame / Obs} \longrightarrow \text{Face Track} \longrightarrow \text{Embedding} \longrightarrow \text{Candidates} \longrightarrow \text{Decision} \longrightarrow \text{Cloud Record}$$

Rather than duplicating high-bandwidth imagery or exposing sensitive raw biometric templates, the system stores lightweight cryptographic hashes, stage references, candidate rankings, and model versions.

---

## 2. 7-Stage Lineage Graph

```
┌─────────────────────────┐
│   1. Camera Ingestion   │  camera_id, zone, camera_config_version
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  2. Frame Acquisition   │  frame_reference, observation_count
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    3. Face Tracking     │  track_id, observation_ids [obs_01, obs_02, ...]
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ 4. Embedding Extraction │  detection_model_version, embedding_model_version,
└────────────┬────────────┘  embedding_fingerprint (SHA-256 digest)
             │
             ▼
┌─────────────────────────┐
│ 5. Candidate Evaluation │  candidate_matches [{identity, score, rank}, ...]
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ 6. Recognition Decision │  selected_identity, confidence, decision_tier
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ 7. Cloud Synchronization│  event_id, cloud_detection_id, provenance_chain_hash
└─────────────────────────┘
```

---

## 3. Privacy & Biometric Protection
- **Zero Raw Vector Exposure**: Raw 512-dimensional floating-point embeddings are **never** serialized or exposed in the provenance JSON or API responses.
- **SHA-256 Fingerprinting**: An irreversible SHA-256 fingerprint ($\text{SHA256}(\text{bytes}(\text{embedding\_vector}))$) is stored to allow verification of mathematical identity without leaking reconstructible facial embeddings.

---

## 4. API Endpoints

### Query Event Lineage
`GET /api/detections/{event_id}/provenance`
Returns the complete 7-stage lineage record, model signatures, candidate scores, and cryptographic chain hash.

### Enforce Retention Policy
`POST /api/provenance/retention`
```json
{
  "max_retention_days": 30
}
```
Purges detailed intermediate processing lineage older than `max_retention_days` while preserving the primary detection audit trail.
