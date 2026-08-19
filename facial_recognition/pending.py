from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np


class PendingSaver:
    """Save unknown face crops and embeddings for later review.

    Saves a .npz per pending item under the provided directory.
    """

    DUPLICATE_THRESHOLD = 0.60
    DEFAULT_UNKNOWN_LABEL_PREFIX = 'Person'

    def __init__(self, base_dir: str | Path = 'pending') -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self._known_unknowns: list[np.ndarray] = []
        self._unknown_labels: list[str] = []
        self._next_unknown_id = 1
        self._load_existing_pending()

    def _parse_label_number(self, label: str) -> Optional[int]:
        if label.startswith(self.DEFAULT_UNKNOWN_LABEL_PREFIX):
            parts = label.split()
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
        return None

    def _parse_label_from_filename(self, filename: str) -> Optional[str]:
        if filename.startswith('pending_'):
            parts = filename[len('pending_'):].split('_')
            if len(parts) >= 2 and parts[0] == self.DEFAULT_UNKNOWN_LABEL_PREFIX and parts[1].isdigit():
                return f'{self.DEFAULT_UNKNOWN_LABEL_PREFIX} {parts[1]}'
        return None

    def _load_existing_pending(self) -> None:
        for path in sorted(self.base.glob('pending_*.npz')):
            try:
                with np.load(path, allow_pickle=True) as data:
                    emb = np.asarray(data['embedding'], dtype=np.float32)
                    if emb.ndim != 1:
                        continue

                    label = None
                    if 'label' in data:
                        raw_label = data['label']
                        if hasattr(raw_label, 'tolist'):
                            try:
                                label = str(raw_label.tolist())
                            except Exception:
                                label = str(raw_label)
                        else:
                            label = str(raw_label)

                    if not label:
                        label = self._parse_label_from_filename(path.name)

                    if not label:
                        label = f'{self.DEFAULT_UNKNOWN_LABEL_PREFIX} {self._next_unknown_id}'

                    self._known_unknowns.append(emb)
                    self._unknown_labels.append(label)
                    parsed = self._parse_label_number(label)
                    if parsed is not None:
                        self._next_unknown_id = max(self._next_unknown_id, parsed + 1)
                    else:
                        self._next_unknown_id = max(self._next_unknown_id, len(self._unknown_labels) + 1)
            except Exception:
                continue

    def _find_matching_label(self, emb: np.ndarray) -> Optional[str]:
        if not self._known_unknowns:
            return None

        emb = np.asarray(emb, dtype=np.float32)
        emb_norm = np.linalg.norm(emb) + 1e-10
        for existing, label in zip(self._known_unknowns, self._unknown_labels):
            sim = float(np.dot(existing, emb) / (np.linalg.norm(existing) * emb_norm))
            if sim >= self.DUPLICATE_THRESHOLD:
                return label
        return None

    def save(self, embedding: np.ndarray, face_image: np.ndarray) -> Optional[str]:
        try:
            emb_arr = np.asarray(embedding, dtype=np.float32)
            if emb_arr.ndim != 1:
                return None

            existing_label = self._find_matching_label(emb_arr)
            if existing_label is not None:
                return existing_label

            label = f'{self.DEFAULT_UNKNOWN_LABEL_PREFIX} {self._next_unknown_id}'
            ts = int(time.time() * 1000)
            fname = f'pending_{label.replace(" ", "_")}_{ts}.npz'
            path = self.base / fname
            img = np.asarray(face_image)
            np.savez_compressed(path, embedding=emb_arr, image=img, label=label)
            self._known_unknowns.append(emb_arr)
            self._unknown_labels.append(label)
            self._next_unknown_id += 1
            return label
        except Exception:
            return None
