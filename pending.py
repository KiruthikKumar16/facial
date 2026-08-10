from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np


class PendingSaver:
    """Save unknown face crops and embeddings for later review.

    Saves a .npz per pending item under the provided directory.
    """

    DUPLICATE_THRESHOLD = 0.92

    def __init__(self, base_dir: str | Path = 'pending') -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self._known_unknowns: list[np.ndarray] = []
        self._load_existing_pending()

    def _load_existing_pending(self) -> None:
        for path in sorted(self.base.glob('pending_*.npz')):
            try:
                with np.load(path, allow_pickle=True) as data:
                    emb = np.asarray(data['embedding'], dtype=np.float32)
                    if emb.ndim == 1:
                        self._known_unknowns.append(emb)
            except Exception:
                continue

    def _is_duplicate(self, emb: np.ndarray) -> bool:
        if not self._known_unknowns:
            return False
        emb = np.asarray(emb, dtype=np.float32)
        emb_norm = np.linalg.norm(emb) + 1e-10
        for existing in self._known_unknowns:
            sim = float(np.dot(existing, emb) / (np.linalg.norm(existing) * emb_norm))
            if sim >= self.DUPLICATE_THRESHOLD:
                return True
        return False

    def save(self, embedding: np.ndarray, face_image: np.ndarray) -> Optional[Path]:
        try:
            emb_arr = np.asarray(embedding, dtype=np.float32)
            if self._is_duplicate(emb_arr):
                return None

            ts = int(time.time() * 1000)
            fname = f'pending_{ts}.npz'
            path = self.base / fname
            img = np.asarray(face_image)
            np.savez_compressed(path, embedding=emb_arr, image=img)
            self._known_unknowns.append(emb_arr)
            return path
        except Exception:
            return None
