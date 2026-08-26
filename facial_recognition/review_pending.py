"""CLI to review pending unknown faces and add them to the gallery.

Usage:
    python review_pending.py

Shows each pending item, opens the image, prompts for a name (or empty to skip),
and if named moves the image into `known_faces/<name>/` and appends embedding to gallery.
"""
from pathlib import Path
from typing import Dict, Optional
import numpy as np
import cv2


PROJECT_ROOT = Path(__file__).resolve().parent
PENDING_DIR = PROJECT_ROOT / 'pending'
GALLERY_PATH = PROJECT_ROOT / 'known_faces' / 'gallery.npz'
KNOWN_DIR = PROJECT_ROOT / 'known_faces'
REUSE_NAME_THRESHOLD = 0.35
DEFAULT_UNKNOWN_LABEL_PREFIX = 'Person'


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


def extract_label(data: np.ndarray, filename: str) -> str:
    if 'label' in data:
        raw_label = data['label']
        if hasattr(raw_label, 'tolist'):
            try:
                return str(raw_label.tolist())
            except Exception:
                return str(raw_label)
        return str(raw_label)

    if filename.startswith('pending_'):
        parts = filename[len('pending_'):].split('_')
        if len(parts) >= 2 and parts[0] == DEFAULT_UNKNOWN_LABEL_PREFIX and parts[1].isdigit():
            return f'{DEFAULT_UNKNOWN_LABEL_PREFIX} {parts[1]}'

    return f'{DEFAULT_UNKNOWN_LABEL_PREFIX} 0'


def find_similar_pending_name(emb: np.ndarray, pending_names: Dict[str, np.ndarray]) -> Optional[str]:
    if not pending_names:
        return None

    labels = list(pending_names.keys())
    embs = np.stack([pending_names[name] for name in labels], axis=0)
    similarities = np.dot(embs, emb) / (
        np.linalg.norm(embs, axis=1) * np.linalg.norm(emb) + 1e-10
    )
    best_index = int(np.argmax(similarities))
    best_score = float(similarities[best_index])
    if best_score >= REUSE_NAME_THRESHOLD:
        return labels[best_index]
    return None


def review() -> None:
    if not PENDING_DIR.exists():
        print('No pending directory found.')
        return

    items = sorted(PENDING_DIR.glob('pending_*.npz'))
    if not items:
        print('No pending items to review.')
        return

    recent_names: Dict[str, np.ndarray] = {}
    auto_accept_names = set()
    for item in items:
        with np.load(item, allow_pickle=True) as data:
            img = data['image']
            emb = data['embedding']
            label = extract_label(data, item.name)

        suggested_name = find_similar_pending_name(emb, recent_names)
        if suggested_name is not None:
            if suggested_name in auto_accept_names:
                name = suggested_name
                print(f'Auto-accepting {item.name} as {name}')
            else:
                win = 'review'
                cv2.imshow(win, img)
                print(f'Suggested name for {item.name} based on prior review: {suggested_name}')
                print("Press 'y' or Enter in the image window to accept (this covers all future matches), or any other key to enter a new name.")
                key = cv2.waitKey(0) & 0xFF
                cv2.destroyWindow(win)
                
                if key in (13, 10, ord('y'), ord('Y'), ord(' ')):
                    auto_accept_names.add(suggested_name)
                    name = suggested_name
                else:
                    name = input(
                        f'Current default label is "{label}". Enter a new name in terminal to change it, or press Enter to keep it: '
                    ).strip()
                if not name:
                    name = label
        else:
            win = 'review'
            cv2.imshow(win, img)
            print(
                f'Reviewing {item.name} (default label: {label}) — press any key in image window to continue, then enter name.'
            )
            cv2.waitKey(0)
            cv2.destroyWindow(win)
            name = input(
                f'Enter name to enroll, or press Enter to keep "{label}" (skip by typing "skip"): '
            ).strip()
            if name.lower() == 'skip':
                print('Skipped')
                continue
            if not name:
                name = label

        person_dir = KNOWN_DIR / name
        person_dir.mkdir(parents=True, exist_ok=True)
        outimg = person_dir / f'{item.stem}.png'
        cv2.imwrite(str(outimg), img)
        append_to_gallery(name, emb)

        recent_names[name] = emb
        item.unlink()
        print(f'Added {name} and removed pending item {item.name}')


if __name__ == '__main__':
    review()
