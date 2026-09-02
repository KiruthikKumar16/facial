"""
Hierarchical Edge/Cloud Vector Search Engine.

Combines a fast local indexed gallery cache at the edge with a comprehensive
cloud vector database for uncertain, stale, or unresolved identities.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SearchTier(str, enum.Enum):
    """The search tier that resolved the identity."""
    LOCAL_HIGH_CONFIDENCE = "LOCAL_HIGH_CONFIDENCE"  # Resolved locally with high confidence
    CLOUD_RESOLVED = "CLOUD_RESOLVED"                # Escalated to cloud and resolved
    LOCAL_FALLBACK = "LOCAL_FALLBACK"                # Cloud offline or timed out; fell back to local
    UNKNOWN = "UNKNOWN"                              # Not matched at either tier


@dataclass
class SearchResult:
    """Result of hierarchical edge/cloud vector search."""
    identity: str
    confidence: float
    search_tier: SearchTier
    gallery_version: int
    local_latency_ms: float
    cloud_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    bandwidth_used_bytes: int = 0
    bandwidth_saved_bytes: int = 0
    cloud_match_found: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "confidence": round(self.confidence, 4),
            "search_tier": self.search_tier.value,
            "gallery_version": self.gallery_version,
            "local_latency_ms": round(self.local_latency_ms, 3),
            "cloud_latency_ms": round(self.cloud_latency_ms, 3),
            "total_latency_ms": round(self.total_latency_ms, 3),
            "bandwidth_used_bytes": self.bandwidth_used_bytes,
            "bandwidth_saved_bytes": self.bandwidth_saved_bytes,
            "cloud_match_found": self.cloud_match_found,
            "notes": self.notes,
        }


@dataclass
class LocalGallery:
    """Versioned local face embedding gallery cache at the edge."""
    version: int = 1
    labels: List[str] = field(default_factory=list)
    embeddings: np.ndarray = field(default_factory=lambda: np.zeros((0, 512), dtype=np.float32))
    profile_ids: List[str] = field(default_factory=list)
    last_synced_at: float = field(default_factory=time.time)

    def size(self) -> int:
        return len(self.labels)

    def save(self, file_path: str | Path) -> None:
        """Save gallery to local disk cache (.npz)."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            version=np.array([self.version], dtype=np.int32),
            labels=np.array(self.labels, dtype=object),
            embeddings=self.embeddings,
            profile_ids=np.array(self.profile_ids, dtype=object),
            last_synced_at=np.array([self.last_synced_at], dtype=np.float64),
        )

    @classmethod
    def load(cls, file_path: str | Path) -> LocalGallery:
        """Load gallery from local disk cache (.npz)."""
        path = Path(file_path)
        if not path.exists():
            return cls()
        try:
            data = np.load(path, allow_pickle=True)
            version = int(data["version"][0]) if "version" in data else 1
            labels = list(data["labels"]) if "labels" in data else []
            embeddings = data["embeddings"] if "embeddings" in data else np.zeros((0, 512), dtype=np.float32)
            profile_ids = list(data["profile_ids"]) if "profile_ids" in data else []
            last_synced = float(data["last_synced_at"][0]) if "last_synced_at" in data else time.time()
            return cls(
                version=version,
                labels=labels,
                embeddings=np.asarray(embeddings, dtype=np.float32),
                profile_ids=profile_ids,
                last_synced_at=last_synced,
            )
        except Exception as e:
            logger.error(f"Failed to load local gallery from {file_path}: {e}")
            return cls()

    def update(
        self,
        labels: List[str],
        embeddings: np.ndarray | List[List[float]],
        version: Optional[int] = None,
        profile_ids: Optional[List[str]] = None,
    ) -> None:
        """Update gallery in memory and bump version."""
        self.labels = list(labels)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        if self.embeddings.ndim == 1 and len(self.labels) > 0:
            self.embeddings = self.embeddings.reshape(1, -1)
        self.profile_ids = list(profile_ids) if profile_ids else [f"prof_{i}" for i in range(len(self.labels))]
        self.version = version if version is not None else (self.version + 1)
        self.last_synced_at = time.time()

    def search(self, query_embedding: np.ndarray) -> Tuple[str, float, int]:
        """
        Perform fast normalized cosine similarity search.
        
        Returns:
            Tuple of (best_identity, similarity_score, best_index)
        """
        if self.embeddings.shape[0] == 0:
            return "Unknown", 0.0, -1

        query = np.asarray(query_embedding, dtype=np.float32).flatten()
        q_norm = np.linalg.norm(query)
        if q_norm < 1e-6:
            return "Unknown", 0.0, -1

        dot_prods = np.dot(self.embeddings, query)
        norms = np.linalg.norm(self.embeddings, axis=1) * q_norm + 1e-10
        similarities = dot_prods / norms

        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])
        best_label = self.labels[best_idx] if best_idx < len(self.labels) else "Unknown"

        return best_label, best_score, best_idx


class HierarchicalSearchEngine:
    """
    Hierarchical Vector Search Engine.
    
    Decision Algorithm:
    1. Local Search: Computes cosine similarity against local gallery cache.
    2. High Confidence (>= local_high_threshold): Immediate local resolution (no network, 0 cloud bandwidth).
    3. Uncertain (local_uncertain_threshold <= score < local_high_threshold) OR Unknown (score < local_uncertain_threshold):
       Escalates to cloud pgvector endpoint passing only the 512-d float embedding vector (2 KB vs 200 KB image).
    4. Offline Resilient: If cloud is unreachable, falls back gracefully to local decision.
    """

    RAW_IMAGE_AVG_BYTES = 200_000  # Approx 200 KB per raw JPEG frame
    EMBEDDING_VECTOR_BYTES = 2048  # 512 floats * 4 bytes = 2 KB

    def __init__(
        self,
        gallery_path: Optional[str | Path] = None,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        local_high_confidence_threshold: float = 0.65,
        local_uncertain_threshold: float = 0.40,
        cloud_recognition_threshold: float = 0.50,
        max_staleness_seconds: float = 3600.0,  # 1 hour
        cloud_search_fn: Optional[Callable[[List[float]], Dict[str, Any]]] = None,
    ) -> None:
        self.gallery_path = Path(gallery_path) if gallery_path else None
        self.api_url = (api_url or os.environ.get("API_URL", "http://localhost:1223")).rstrip("/")
        self.api_key = api_key or os.environ.get("EDGE_API_KEY", "default-dev-key")
        
        self.local_high_threshold = float(local_high_confidence_threshold)
        self.local_uncertain_threshold = float(local_uncertain_threshold)
        self.cloud_threshold = float(cloud_recognition_threshold)
        self.max_staleness_seconds = float(max_staleness_seconds)
        self.cloud_search_fn = cloud_search_fn

        # Load local gallery
        if self.gallery_path and self.gallery_path.exists():
            self.gallery = LocalGallery.load(self.gallery_path)
        else:
            self.gallery = LocalGallery()

        # Cumulative Metrics
        self.metrics = {
            "total_searches": 0,
            "local_hits": 0,
            "cloud_queries": 0,
            "cloud_hits": 0,
            "fallbacks": 0,
            "unknowns": 0,
            "total_bandwidth_saved_bytes": 0,
            "total_local_latency_ms": 0.0,
            "total_cloud_latency_ms": 0.0,
        }

    @property
    def gallery_version(self) -> int:
        return self.gallery.version

    def is_gallery_stale(self) -> bool:
        return (time.time() - self.gallery.last_synced_at) > self.max_staleness_seconds

    def sync_gallery_from_backend(self) -> bool:
        """Fetch latest active gallery and version from backend API."""
        endpoint = f"{self.api_url}/api/internal/gallery"
        try:
            req = urllib.request.Request(
                endpoint,
                headers={"X-API-Key": self.api_key},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                labels = data.get("labels", [])
                embeddings = data.get("embeddings", [])
                version = data.get("version", self.gallery.version + 1)
                profile_ids = data.get("profile_ids")

                if labels and embeddings:
                    self.gallery.update(labels=labels, embeddings=embeddings, version=version, profile_ids=profile_ids)
                    if self.gallery_path:
                        self.gallery.save(self.gallery_path)
                    logger.info(f"Synced local gallery v{self.gallery.version} ({len(labels)} identities)")
                    return True
        except Exception as e:
            logger.warning(f"Failed to sync gallery from {endpoint}: {e}")
        return False

    def query_cloud_vector_search(self, embedding: np.ndarray) -> Tuple[Optional[str], float, float]:
        """
        Execute cloud vector search against pgvector gallery.
        
        Returns:
            Tuple of (best_identity_or_none, similarity_score, latency_ms)
        """
        t0 = time.perf_counter()
        
        # Use custom test mock if injected
        if self.cloud_search_fn:
            try:
                res = self.cloud_search_fn(embedding.tolist())
                latency_ms = (time.perf_counter() - t0) * 1000.0
                matches = res.get("matches", [])
                if matches:
                    return matches[0]["identity"], float(matches[0]["score"]), latency_ms
                return None, 0.0, latency_ms
            except Exception as e:
                logger.error(f"Custom cloud search failed: {e}")
                return None, 0.0, (time.perf_counter() - t0) * 1000.0

        # HTTP Cloud Search Call
        endpoint = f"{self.api_url}/api/internal/vector-search"
        payload = json.dumps({
            "embedding": embedding.tolist(),
            "top_k": 1,
            "threshold": self.cloud_threshold,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                endpoint,
                data=payload,
                headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency_ms = (time.perf_counter() - t0) * 1000.0
                matches = data.get("matches", [])
                if matches:
                    best = matches[0]
                    return best["identity"], float(best["score"]), latency_ms
                return None, 0.0, latency_ms
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning(f"Cloud vector search request failed ({endpoint}): {e}")
            return None, 0.0, latency_ms

    def search(
        self,
        embedding: np.ndarray,
        force_cloud: bool = False,
    ) -> SearchResult:
        """
        Hierarchical search decision pipeline.
        """
        t_start = time.perf_counter()
        self.metrics["total_searches"] += 1

        # 1. Local Vector Search
        t_local_start = time.perf_counter()
        local_id, local_score, _ = self.gallery.search(embedding)
        local_latency = (time.perf_counter() - t_local_start) * 1000.0
        self.metrics["total_local_latency_ms"] += local_latency

        # Check conditions
        stale = self.is_gallery_stale()
        should_use_cloud = force_cloud or stale or (local_score < self.local_high_threshold)

        # ---------------- Tier 1: Local High Confidence Match ----------------
        if not should_use_cloud:
            self.metrics["local_hits"] += 1
            # Bandwidth saved: avoided sending image or cloud vector request
            bw_saved = self.RAW_IMAGE_AVG_BYTES
            self.metrics["total_bandwidth_saved_bytes"] += bw_saved
            tot_lat = (time.perf_counter() - t_start) * 1000.0

            return SearchResult(
                identity=local_id,
                confidence=local_score,
                search_tier=SearchTier.LOCAL_HIGH_CONFIDENCE,
                gallery_version=self.gallery.version,
                local_latency_ms=local_latency,
                cloud_latency_ms=0.0,
                total_latency_ms=tot_lat,
                bandwidth_used_bytes=0,
                bandwidth_saved_bytes=bw_saved,
                cloud_match_found=False,
                notes=f"Resolved locally with high confidence ({local_score:.2f} >= {self.local_high_threshold:.2f})",
            )

        # ---------------- Tier 2: Cloud Vector Search Escalation ----------------
        self.metrics["cloud_queries"] += 1
        cloud_id, cloud_score, cloud_latency = self.query_cloud_vector_search(embedding)
        self.metrics["total_cloud_latency_ms"] += cloud_latency
        tot_lat = (time.perf_counter() - t_start) * 1000.0

        # Bandwidth: Sent 512-d vector instead of raw image!
        bw_used = self.EMBEDDING_VECTOR_BYTES
        bw_saved = max(0, self.RAW_IMAGE_AVG_BYTES - self.EMBEDDING_VECTOR_BYTES)
        self.metrics["total_bandwidth_saved_bytes"] += bw_saved

        if cloud_id is not None and cloud_score >= self.cloud_threshold:
            self.metrics["cloud_hits"] += 1
            return SearchResult(
                identity=cloud_id,
                confidence=cloud_score,
                search_tier=SearchTier.CLOUD_RESOLVED,
                gallery_version=self.gallery.version,
                local_latency_ms=local_latency,
                cloud_latency_ms=cloud_latency,
                total_latency_ms=tot_lat,
                bandwidth_used_bytes=bw_used,
                bandwidth_saved_bytes=bw_saved,
                cloud_match_found=True,
                notes=f"Resolved via cloud vector search ({cloud_score:.2f} >= {self.cloud_threshold:.2f})",
            )

        # ---------------- Tier 3: Local Fallback vs Unknown ----------------
        if local_score >= self.local_uncertain_threshold:
            self.metrics["fallbacks"] += 1
            return SearchResult(
                identity=local_id,
                confidence=local_score,
                search_tier=SearchTier.LOCAL_FALLBACK,
                gallery_version=self.gallery.version,
                local_latency_ms=local_latency,
                cloud_latency_ms=cloud_latency,
                total_latency_ms=tot_lat,
                bandwidth_used_bytes=bw_used,
                bandwidth_saved_bytes=bw_saved,
                cloud_match_found=False,
                notes=f"Cloud unresolved; fell back to local candidate ({local_score:.2f})",
            )

        # Unresolved
        self.metrics["unknowns"] += 1
        return SearchResult(
            identity="Unknown",
            confidence=max(local_score, cloud_score),
            search_tier=SearchTier.UNKNOWN,
            gallery_version=self.gallery.version,
            local_latency_ms=local_latency,
            cloud_latency_ms=cloud_latency,
            total_latency_ms=tot_lat,
            bandwidth_used_bytes=bw_used,
            bandwidth_saved_bytes=bw_saved,
            cloud_match_found=False,
            notes="Unresolved across both local gallery and cloud vector database",
        )
