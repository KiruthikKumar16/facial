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
            while True:
                time.sleep(300)
                self._fetch_gallery_from_api(gallery_path)
                
        success = self._fetch_gallery_from_api(gallery_path)
        if not success:
            self._load_from_file(gallery_path)
            
        t = threading.Thread(target=sync, daemon=True)
        t.start()
        
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

    def recognize(self, embedding: np.ndarray) -> tuple[str, float]:
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
            best_index = int(np.argmax(similarities))
            best_score = float(similarities[best_index])

            dur = (time.perf_counter() - start) * 1000.0
            logger.debug('Recognize took %.2f ms, best_score=%.4f, index=%d', dur, best_score, best_index)
            if best_score >= self.threshold and best_index < len(self.labels):
                return self.labels[best_index], best_score

            if self.hierarchical_engine is not None:
                try:
                    res = self.hierarchical_engine.search(norm_query)
                    tier_val = getattr(res.search_tier, 'value', str(res.search_tier))
                    if tier_val in ("CLOUD_RESOLVED", "LOCAL_HIGH_CONFIDENCE") and res.identity != "Unknown":
                        return res.identity, float(res.confidence)
                except Exception as e:
                    logger.warning(f"Hierarchical search fallback failed: {e}")

            return 'Unknown', best_score

