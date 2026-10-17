from typing import Any, Optional, List, Dict, Tuple
import os
import time
import logging
import threading
import urllib.request
import json
import numpy as np


logger = logging.getLogger(__name__)


class Recognizer:
    def __init__(self, gallery_path: str, threshold: float, hierarchical_engine: Any = None) -> None:
        self.threshold = threshold
        self.hierarchical_engine = hierarchical_engine
        self.labels: list[str] = []
        self.embeddings: np.ndarray = np.zeros((0, 512), dtype=np.float32)
        self.lock = threading.RLock()
        self._stop_event = threading.Event()
        self._sync_thread: Optional[threading.Thread] = None
        self._load_gallery(gallery_path)

    def _normalize_embeddings(self, embs: np.ndarray) -> np.ndarray:
        """Pre-normalize embeddings so cosine similarity is a fast single matrix-vector dot product."""
        if embs.shape[0] == 0:
            return np.zeros((0, 512), dtype=np.float32)
        arr = np.asarray(embs, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-10
        return (arr / norms).astype(np.float32)

    def _load_gallery(self, gallery_path: str) -> None:
        if not gallery_path:
            return
        def sync():
            while not self._stop_event.is_set():
                if self._stop_event.wait(300):
                    break
                self._fetch_gallery_from_api(gallery_path)
                
        success = self._fetch_gallery_from_api(gallery_path)
        if not success:
            self._load_from_file(gallery_path)
            
        self._sync_thread = threading.Thread(target=sync, daemon=True)
        self._sync_thread.start()

    def stop(self) -> None:
        """Stop background sync thread."""
        self._stop_event.set()

    def close(self) -> None:
        """Alias for stop."""
        self.stop()
        
    def _fetch_gallery_from_api(self, fallback_path: str) -> bool:
        api_url = os.environ.get("API_URL", "http://localhost:1223").rstrip('/')
        api_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
        try:
            req = urllib.request.Request(f"{api_url}/api/internal/gallery", headers={"X-API-Key": api_key})
            with urllib.request.urlopen(req, timeout=5.0) as response:
                data = json.loads(response.read().decode())
                
                labels = data.get("labels", [])
                embeddings = data.get("embeddings", [])
                
                if labels and embeddings:
                    norm_embs = self._normalize_embeddings(np.asarray(embeddings, dtype=np.float32))
                    with self.lock:
                        self.labels = labels
                        self.embeddings = norm_embs

                    if fallback_path:
                        try:
                            np.savez(fallback_path, labels=self.labels, embeddings=self.embeddings)
                        except Exception as e:
                            logger.warning(f"Failed to save gallery cache: {e}")
                            
                    logger.info(f"Synced gallery from API: {len(labels)} identities.")
                    return True
        except Exception as e:
            logger.warning(f"Failed to sync gallery from API: {e}")
        return False

    def _load_from_file(self, gallery_path: str) -> None:
        if not gallery_path or not os.path.exists(gallery_path):
            with self.lock:
                self.labels = []
                self.embeddings = np.zeros((0, 512), dtype=np.float32)
            return

        try:
            gallery = np.load(gallery_path, allow_pickle=True)
            labels = gallery['labels'].tolist() if 'labels' in gallery else []
            embeddings = gallery['embeddings'] if 'embeddings' in gallery else np.zeros((0, 512), dtype=np.float32)
            norm_embs = self._normalize_embeddings(embeddings)
            with self.lock:
                self.labels = labels
                self.embeddings = norm_embs
            logger.info(f"Loaded gallery from local cache: {len(self.labels)} identities.")
        except Exception as e:
            logger.error(f"Error loading local gallery cache: {e}")
            with self.lock:
                self.labels = []
                self.embeddings = np.zeros((0, 512), dtype=np.float32)

    def recognize(
        self,
        embedding: np.ndarray,
        pose_meta: Optional[Dict[str, Any]] = None,
        min_confidence: Optional[float] = None,
    ) -> tuple[str, float]:
        start = time.perf_counter()
        with self.lock:
            q_norm = np.linalg.norm(embedding)
            if q_norm < 1e-6:
                return 'Unknown', 0.0
            norm_query = (embedding / q_norm).astype(np.float32)

            if self.embeddings.shape[0] == 0 or len(self.labels) == 0:
                logger.debug('No gallery embeddings available')
                if self.hierarchical_engine is not None:
                    try:
                        res = self.hierarchical_engine.search(norm_query)
                        tier_val = getattr(res.search_tier, 'value', str(res.search_tier))
                        if tier_val in ("CLOUD_RESOLVED", "LOCAL_HIGH_CONFIDENCE") and res.identity != "Unknown":
                            return res.identity, float(res.confidence)
                    except Exception as e:
                        logger.warning(f"Hierarchical search fallback failed: {e}")
                return 'Unknown', 0.0

            similarities = np.dot(self.embeddings, norm_query)

            # Universal CCTV Multi-Exemplar Aggregation:
            # Group highest similarity per identity to handle multi-angle enrollments
            scores_by_label: Dict[str, float] = {}
            for idx, label in enumerate(self.labels):
                sim = float(similarities[idx])
                if label not in scores_by_label or sim > scores_by_label[label]:
                    scores_by_label[label] = sim

            sorted_candidates = sorted(scores_by_label.items(), key=lambda x: x[1], reverse=True)
            if not sorted_candidates:
                return 'Unknown', 0.0

            best_label, best_score = sorted_candidates[0]
            second_score = sorted_candidates[1][1] if len(sorted_candidates) > 1 else -1.0
            margin = best_score - second_score if second_score >= 0 else 1.0

            dur = (time.perf_counter() - start) * 1000.0
            logger.debug('Recognize took %.2f ms, best=%s (%.4f), margin=%.4f', dur, best_label, best_score, margin)

            # 1. Direct standard threshold match
            # If min_confidence is explicitly passed (e.g. cluster centroid re-identification), use it
            if min_confidence is not None:
                effective_threshold = float(min_confidence)
            else:
                # Require minimum 0.58 for reliable 1:N CCTV gallery matching to eliminate false hits
                effective_threshold = max(0.58, self.threshold)

            if best_score >= effective_threshold:
                return best_label, best_score

            # 2. Universal CCTV Angle-Adaptive Margin-Gated Match:
            # When looking down from ceiling/desk view, cosine similarity drops ~0.05-0.08.
            # Only accept match if there is a wide margin (>= 0.12) over the nearest competitor and no blind scalp.
            if pose_meta:
                pitch = float(pose_meta.get("pitch_ratio", 0.85))
                is_steep = bool(pose_meta.get("is_steep_scalp", False))
                if (pitch < 0.60 or pitch > 1.15) and not is_steep and margin >= 0.12:
                    adaptive_thresh = max(0.55, effective_threshold - 0.05)
                    if best_score >= adaptive_thresh:
                        logger.info("Universal CCTV angle-adaptive match: %s (score=%.4f, thresh=%.4f, margin=%.4f)",
                                    best_label, best_score, adaptive_thresh, margin)
                        return best_label, best_score

            if self.hierarchical_engine is not None:
                try:
                    res = self.hierarchical_engine.search(norm_query)
                    tier_val = getattr(res.search_tier, 'value', str(res.search_tier))
                    if tier_val in ("CLOUD_RESOLVED", "LOCAL_HIGH_CONFIDENCE") and res.identity != "Unknown":
                        return res.identity, float(res.confidence)
                except Exception as e:
                    logger.warning(f"Hierarchical search fallback failed: {e}")

            return 'Unknown', best_score

    def match(self, embedding: np.ndarray, pose_meta: Optional[Dict[str, Any]] = None) -> tuple[str, float]:
        """Alias for recognize method."""
        return self.recognize(embedding, pose_meta=pose_meta)

