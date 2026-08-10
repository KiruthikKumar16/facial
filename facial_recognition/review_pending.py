"""CLI to review pending unknown faces and add them to the gallery.

Usage:
    python review_pending.py

Shows each pending item, opens the image, prompts for a name (or empty to skip),
and if named moves the image into `known_faces/<name>/` and appends embedding to gallery.
"""
from pathlib import Path
from typing import List
import shutil
import numpy as np
import cv2


PENDING_DIR = Path('pending')
GALLERY_PATH = Path('known_faces/gallery.npz')
KNOWN_DIR = Path('known_faces')


def append_to_gallery(name: str, emb: np.ndarray) -> None:
    if GALLERY_PATH.exists():
        data = np.load(GALLERY_PATH, allow_pickle=True)
        labels = list(data['labels']) if 'labels' in data else []
        embs = np.asarray(data['embeddings']) if 'embeddings' in data else np.zeros((0, emb.shape[0]), dtype=np.float32)
    else:
        labels = []
        embs = np.zeros((0, emb.shape[0]), dtype=np.float32)

    labels.append(name)
    if embs.size == 0:
        embs = np.asarray([emb], dtype=np.float32)
    else:
        embs = np.vstack([embs, np.asarray(emb, dtype=np.float32)])

    np.savez_compressed(GALLERY_PATH, labels=np.array(labels, dtype=object), embeddings=embs)


def review() -> None:
    if not PENDING_DIR.exists():
        print('No pending directory found.')
        return

    items = sorted(PENDING_DIR.glob('pending_*.npz'))
    if not items:
        print('No pending items to review.')
        return

    for item in items:
        data = np.load(item, allow_pickle=True)
        img = data['image']
        emb = data['embedding']

        win = 'review'
        cv2.imshow(win, img)
        print(f'Reviewing {item.name} — press any key in image window to continue, then enter name (empty=skip):')
        cv2.waitKey(0)
        cv2.destroyWindow(win)
        name = input('Enter name (or leave empty to skip): ').strip()
        if not name:
            print('Skipped')
            continue

        # ensure known dir exists
        person_dir = KNOWN_DIR / name
        person_dir.mkdir(parents=True, exist_ok=True)
        # save image into person dir
        outimg = person_dir / f'{item.stem}.png'
        cv2.imwrite(str(outimg), img)
        # append embedding to gallery
        append_to_gallery(name, emb)
        # remove pending file
        item.unlink()
        print(f'Added {name} and removed pending item {item.name}')


if __name__ == '__main__':
    review()
