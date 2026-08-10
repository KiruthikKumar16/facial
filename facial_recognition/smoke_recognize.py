"""Capture one frame from webcam, extract embedding with buffalo_l, compare to gallery.npz.
Run: ./myenv/Scripts/python.exe smoke_recognize.py
"""
from typing import Any, List, Tuple, cast
from pathlib import Path
import logging

import cv2
import numpy as np
from numpy.typing import NDArray

# insightface lacks type stubs in this environment; ignore that check for runtime import
from insightface.app import FaceAnalysis  # type: ignore[reportMissingTypeStubs]

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('smoke')

GALLERY = Path('known_faces/gallery.npz')
MODEL = 'buffalo_l'


def load_gallery(path: Path) -> Tuple[List[str], NDArray[np.float32]]:
    if not path.exists():
        log.error('Gallery not found at %s', path)
        return [], np.zeros((0, 512), dtype=np.float32)
    g = np.load(path, allow_pickle=True)
    labels = cast(List[str], list(g['labels'])) if 'labels' in g else []
    embs = g['embeddings'] if 'embeddings' in g else np.zeros((0, 512), dtype=np.float32)
    embs = np.asarray(embs, dtype=np.float32)
    if embs.ndim == 1:
        embs = embs.reshape(1, -1)
    log.info('Loaded gallery: %d labels, embeddings shape %s', len(labels), embs.shape)
    return labels, embs


def compare(embs: NDArray[np.float32], emb: NDArray[np.float32]) -> List[Tuple[int, float]]:
    if embs.shape[0] == 0:
        return []
    # cosine similarity: (a @ b) / (||a|| * ||b||)
    norms = np.linalg.norm(embs, axis=1)
    emb_norm = np.linalg.norm(emb) + 1e-10
    sims = (embs @ emb) / (norms * emb_norm)
    order = np.argsort(-sims)
    return [(int(i), float(sims[int(i)])) for i in order]


def main() -> None:
    labels, gallery = load_gallery(GALLERY)

    app: Any = FaceAnalysis(name=MODEL)
    app.prepare(ctx_id=-1)
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        log.error('Could not open webcam (0)')
        raise SystemExit(1)

    # warmup
    for _ in range(3):
        _ = cam.read()

    ret, frame = cam.read()
    if not ret:
        log.error('Failed to capture frame')
        raise SystemExit(1)

    faces = app.get(frame)
    log.info('Detected %d faces', len(faces))
    if not faces:
        # try resizing a bit and re-run
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (w // 2, h // 2))
        faces = app.get(small)
        log.info('Retry detected %d faces', len(faces))
        if not faces:
            log.error('No faces detected, aborting')
            raise SystemExit(1)

    for idx, face in enumerate(faces):
        emb = np.asarray(getattr(face, 'embedding'), dtype=np.float32)
        results = compare(gallery, emb)
        if not results:
            log.info('Face %d: no gallery', idx)
            continue
        top_idx, top_score = results[0]
        top_label = labels[top_idx] if top_idx < len(labels) else '<unknown>'
        log.info('Face %d: top match: %s (score=%.4f, index=%d)', idx, top_label, top_score, top_idx)
        # print top 5
        for r_i, r_s in results[:5]:
            lab = labels[r_i] if r_i < len(labels) else '<unknown>'
            print(f'top: {lab} ({r_s:.4f})')

    cam.release()


if __name__ == '__main__':
    main()
