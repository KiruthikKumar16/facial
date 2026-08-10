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
        except Exception:
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
