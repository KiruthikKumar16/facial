# AI Model & Configuration Version Tracking: Auditability & Reproducibility Guide

## 1. Executive Summary
In high-consequence facial recognition and security systems, a recognition score is meaningless without context:
- Which face detector detected the face?
- Which neural backbone extracted the feature embedding vector?
- What enrolled gallery snapshot was active at the time?
- What similarity thresholds and camera profiles were in effect?
- Which temporal / fusion algorithm made the final classification?

This document outlines the complete immutable version tracking architecture that guarantees forensic auditability, cryptographic integrity, and bitwise reproducibility across the entire detection lifecycle.

---

## 2. Tracked Version Components

Every persisted recognition event (both in local edge ledger and cloud PostgreSQL database) contains the following 6 version identifiers:

| Component | Identifier Example | Purpose |
| :--- | :--- | :--- |
| **Detection Model Version** | `scrfd_500m_bnkps_v1` | Identifies face detection model weights, resolution, and landmark extraction logic. |
| **Embedding Model Version** | `w600k_mbf_v1` | Identifies feature extractor backbone (e.g. MobileFaceNet vs. ResNet-100) defining metric vector space. |
| **Gallery Version** | `1` (or integer count/hash) | Identifies snapshot of enrolled identities against which search was executed. |
| **Threshold Version** | `1` | Snapshot version of active similarity, quality, and liveness thresholds. |
| **Camera Config Version** | `1` (or camera profile ver) | Profile version containing per-camera shutter/exposure, ROI, and local temporal window parameters. |
| **Algorithm Version** | `temporal_fusion_v2` | Version of fusion engine (e.g. single-frame vs. quality-weighted multi-observation fusion). |
| **Bundle Fingerprint Hash** | SHA-256 (`e3b0c44...`) | Cryptographic digest anchoring all 6 version parameters simultaneously. |

---

## 3. Embedding Incompatibility Prevention

### The Problem
Neural network face embeddings from different models (e.g., `MobileFaceNet` 512-d vs. `ArcFace ResNet100` 512-d vs. `MobileNetV2` 256-d) cannot be mathematically compared using cosine similarity or Euclidean distance, even if they share the same dimensional size. Comparing vectors across mismatched models yields random, unpredictable similarity scores that cause silent, unexplainable false matches or rejections.

### Enforcement Mechanism
The `EmbeddingVersionValidator` enforces strict pre-comparison validation:
1. **Mathematical Validation**: Rejects comparisons between differing model architectures or dimensions (`IncompatibleEmbeddingModelError`).
2. **Cloud API Safeguard**: `/api/internal/vector-search` filters candidate embeddings by `model_version`, skipping any incompatible vectors stored from previous migrations.
3. **Migration Manager (`ModelMigrationManager`)**: Allows dual-model enrollment during rolling upgrades without risking cross-model vector collisions.

---

## 4. Cryptographic Tamper-Evident Chaining

All 6 version fields are incorporated into the canonical serialization of each detection event:

```python
payload = {
    "event_id": event_id,
    "device_id": device_id,
    "camera_id": camera_id,
    "sequence_number": sequence_number,
    "capture_timestamp": capture_timestamp,
    "identity": identity,
    "confidence": round(confidence, 6),
    "event_payload": event_payload,
    "detection_model_version": detection_model_version,
    "embedding_model_version": embedding_model_version,
    "gallery_version": gallery_version,
    "threshold_version": threshold_version,
    "config_version": config_version,
    "algorithm_version": algorithm_version,
    "bundle_hash": bundle_hash,
    "previous_event_hash": previous_event_hash
}
```

If an attacker or corrupted process modifies the recorded model version or threshold version after the fact to justify a false match, the cryptographic event hash immediately breaks, triggering an integrity violation alert during ledger validation.

---

## 5. Historical Reproducibility Protocol

To reproduce a historical recognition event during an audit:
1. Extract the recorded `detection_model_version`, `embedding_model_version`, `camera_config_version`, and `algorithm_version` from the event record.
2. Load the corresponding frozen model weights and parameter profile from the artifact registry.
3. Re-run inference with the original raw frame or cached landmarks.
4. Verify that the newly generated feature vector matches the recorded embedding and produces the exact same classification decision.
