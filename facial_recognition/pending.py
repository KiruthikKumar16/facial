from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import cv2


class PendingSaver:
    """Save unknown face crops and embeddings for later review.

    Saves a .npz per pending item under the provided directory.
    """

    def __init__(self, base_dir: str | Path = 'pending') -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, embedding: np.ndarray, face_image: np.ndarray) -> Optional[Path]:
        try:
            ts = int(time.time() * 1000)
            fname = f'pending_{ts}.npz'
            path = self.base / fname
            # ensure image is BGR ndarray
            img = np.asarray(face_image)
            # store embedding and image
            np.savez_compressed(path, embedding=np.asarray(embedding, dtype=np.float32), image=img)
            return path
        except Exception:
            return None
