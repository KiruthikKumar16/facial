import os
import time
import logging

import numpy as np


logger = logging.getLogger(__name__)


class Recognizer:
    def __init__(self, gallery_path: str, threshold: float) -> None:
        self.threshold = threshold
        self.labels: list[str] = []
        self.embeddings: np.ndarray = np.zeros((0, 512), dtype=np.float32)
        self._load_gallery(gallery_path)

    def _load_gallery(self, gallery_path: str) -> None:
        import threading
        
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
        import urllib.request
        import json
        api_url = os.environ.get("API_URL", "http://localhost:8000").rstrip('/')
        api_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
        try:
            req = urllib.request.Request(f"{api_url}/api/internal/gallery", headers={"X-API-Key": api_key})
            with urllib.request.urlopen(req, timeout=5.0) as response:
                data = json.loads(response.read().decode())
                
                labels = data.get("labels", [])
                embeddings = data.get("embeddings", [])
                
                if labels and embeddings:
                    self.labels = labels
                    self.embeddings = np.asarray(embeddings, dtype=np.float32)
                    if self.embeddings.ndim == 1:
                        self.embeddings = self.embeddings.reshape(1, -1)
                        
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
            self.labels = []
            self.embeddings = np.zeros((0, 512), dtype=np.float32)
            return

        try:
            gallery = np.load(gallery_path, allow_pickle=True)
            self.labels = gallery['labels'].tolist() if 'labels' in gallery else []
            embeddings = gallery['embeddings'] if 'embeddings' in gallery else np.zeros((0, 512), dtype=np.float32)
            self.embeddings = np.asarray(embeddings, dtype=np.float32)
            if self.embeddings.ndim == 1:
                self.embeddings = self.embeddings.reshape(1, -1)
            logger.info(f"Loaded gallery from local cache: {len(self.labels)} identities.")
        except Exception as e:
            logger.error(f"Error loading local gallery cache: {e}")
            self.labels = []
            self.embeddings = np.zeros((0, 512), dtype=np.float32)

    def recognize(self, embedding: np.ndarray) -> tuple[str, float]:
        start = time.perf_counter()
        if self.embeddings.shape[0] == 0:
            logger.debug('No gallery embeddings available')
            return 'Unknown', 0.0

        similarities = np.dot(self.embeddings, embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(embedding) + 1e-10
        )
        best_index = int(np.argmax(similarities))
        best_score = float(similarities[best_index])
        dur = (time.perf_counter() - start) * 1000.0
        logger.debug('Recognize took %.2f ms, best_score=%.4f, index=%d', dur, best_score, best_index)
        if best_score >= self.threshold and best_index < len(self.labels):
            return self.labels[best_index], best_score
        return 'Unknown', best_score
