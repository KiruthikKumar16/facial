import os
import sys
from pathlib import Path
from typing import Any, cast, Dict, Iterable

import cv2
import numpy as np
from insightface.app import FaceAnalysis  # type: ignore[reportMissingTypeStubs]


def find_image_files(folder_path: Path) -> Iterable[Path]:
    for root, _, files in os.walk(folder_path):
        for filename in files:
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                yield Path(root) / filename


def build_gallery(known_faces_dir: Path, gallery_path: Path, use_gpu: bool, det_size: tuple[int, int]) -> None:
    if not known_faces_dir.exists() or not known_faces_dir.is_dir():
        raise FileNotFoundError(f'Known faces directory not found: {known_faces_dir}')

    providers = ['CUDAExecutionProvider'] if use_gpu else ['CPUExecutionProvider']
    app: Any = cast(Any, FaceAnalysis(name='buffalo_l', providers=providers))
    app.prepare(ctx_id=0 if use_gpu else -1, det_size=det_size)

    labels: list[str] = []
    embeddings: list[np.ndarray] = []

    for person_dir in sorted(known_faces_dir.iterdir()):
        if not person_dir.is_dir():
            continue
        person_name = person_dir.name
        for image_path in sorted(find_image_files(person_dir)):
            image = cv2.imread(str(image_path))
            if image is None:
                print(f'Warning: unable to read {image_path}, skipping')
                continue
            faces = app.get(image)
            if not faces:
                print(f'Warning: no face detected in {image_path}, skipping')
                continue
            embedding = np.asarray(faces[0].embedding, dtype=np.float32)
            if embedding.size == 0:
                print(f'Warning: no embedding for {image_path}, skipping')
                continue
            labels.append(person_name)
            embeddings.append(embedding)
            print(f'Enrolled {person_name} from {image_path.name}')

    if len(labels) == 0:
        print('No faces enrolled. The gallery will be empty.')
        np.savez_compressed(gallery_path, labels=np.array([], dtype=object), embeddings=np.zeros((0, 512), dtype=np.float32))
    else:
        np.savez_compressed(gallery_path, labels=np.array(labels, dtype=object), embeddings=np.stack(embeddings))
        print(f'Saved gallery with {len(labels)} enrolled faces to {gallery_path}')


def load_yaml_config(path: Path) -> Dict[str, Any]:
    import yaml

    with path.open('r', encoding='utf-8') as stream:
        return yaml.safe_load(stream)


if __name__ == '__main__':
    config_path = Path(__file__).resolve().parent / 'config.yaml'
    config: Dict[str, Any] = load_yaml_config(config_path)
    known_faces_dir = Path(config.get('known_faces_dir', 'known_faces'))
    gallery_path = Path(config.get('gallery_path', 'known_faces/gallery.npz'))
    use_gpu = bool(config.get('use_gpu', False))
    inference_width = int(config.get('inference_frame_width', 640))
    inference_height = int(config.get('inference_frame_height', 640))

    try:
        build_gallery(known_faces_dir, gallery_path, use_gpu, (inference_width, inference_height))
    except Exception as exc:
        print(f'Enrollment failed: {exc}')
        sys.exit(1)
