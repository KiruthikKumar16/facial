import hashlib
import json
from typing import Any, Dict, Optional

class EventHasher:
    """Cryptographic utility for tamper-evident event hashing."""
    
    # The genesis hash for the very first event in a camera's chain
    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    @staticmethod
    def _canonical_serialize(data: Dict[str, Any]) -> str:
        """
        Produce a deterministic canonical string representation of a dictionary.
        Keys are sorted to ensure the same dictionary always produces the same string.
        """
        return json.dumps(data, sort_keys=True, separators=(',', ':'))

    @classmethod
    def compute_hash(
        cls, 
        event_id: str,
        device_id: str,
        camera_id: str,
        sequence_number: int,
        capture_timestamp: str,
        identity: Optional[str],
        confidence: Optional[float],
        event_payload: Optional[str],
        age: Optional[int],
        gender: Optional[str],
        previous_event_hash: str,
        config_version: Optional[int] = 1,
        detection_model_version: Optional[str] = None,
        embedding_model_version: Optional[str] = None,
        gallery_version: Optional[int] = None,
        threshold_version: Optional[int] = None,
        algorithm_version: Optional[str] = None,
        bundle_hash: Optional[str] = None,
    ) -> str:
        """
        Compute the SHA-256 cryptographic hash of an event.
        
        This establishes a tamper-evident chain across all 6 model/config versions:
        detection model, embedding model, gallery version, threshold version,
        camera config version, and algorithm version.
        """
        
        # Build canonical payload
        payload = {
            "event_id": event_id,
            "device_id": device_id,
            "camera_id": camera_id,
            "sequence_number": sequence_number,
            "capture_timestamp": capture_timestamp,
            "identity": identity,
            "confidence": round(confidence, 6) if confidence is not None else None,
            "event_payload": event_payload,
            "age": age,
            "gender": gender,
            "config_version": config_version if config_version is not None else 1,
            "detection_model_version": detection_model_version or "scrfd_500m_bnkps_v1",
            "embedding_model_version": embedding_model_version or "w600k_mbf_v1",
            "gallery_version": gallery_version if gallery_version is not None else 1,
            "threshold_version": threshold_version if threshold_version is not None else 1,
            "algorithm_version": algorithm_version or "temporal_fusion_v2",
            "bundle_hash": bundle_hash,
            "previous_event_hash": previous_event_hash
        }
        
        serialized = cls._canonical_serialize(payload)
        
        # Calculate SHA-256
        hasher = hashlib.sha256()
        hasher.update(serialized.encode('utf-8'))
        return hasher.hexdigest()
