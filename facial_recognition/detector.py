from typing import Any, Dict, List, Optional, Tuple, cast

import cv2
import numpy as np
from insightface.app import FaceAnalysis  # type: ignore[reportMissingTypeStubs]


class InsightFaceDetector:
    def __init__(self, use_gpu: bool, det_size: Tuple[int, int], model_name: str = 'buffalo_l', fast_detector: bool = False) -> None:
        self.use_fast_detector = fast_detector
        self.det_size = det_size
        self.model_name = model_name
        providers = ['CUDAExecutionProvider'] if use_gpu else ['CPUExecutionProvider']

        self.app: Any = FaceAnalysis(name=model_name, providers=providers)
        self.app.prepare(ctx_id=0 if use_gpu else -1, det_size=det_size)

        cv2_any: Any = cv2
        self.use_fast_detector = self.use_fast_detector and hasattr(cv2_any, 'CascadeClassifier') and hasattr(cv2_any, 'data')
        self.cascade: Optional[Any] = None
        if self.use_fast_detector:
            cascade_path = cv2_any.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.cascade = cv2_any.CascadeClassifier(cascade_path)
            if self.cascade is None or self.cascade.empty():
                print(f'Warning: could not load Haar cascade at {cascade_path}; disabling fast detector.')
                self.use_fast_detector = False
                self.cascade = None

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if self.use_fast_detector and self.cascade is not None:
            # Use a fast Haar cascade as a gate, then run the full face model only when at least one candidate face appears.
            scale_factor = 320 / max(frame.shape[:2])
            small = cv2.resize(frame, (0, 0), fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_LINEAR)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            try:
                faces = cast(List[Any], self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)))
            except Exception:
                faces = []
            if len(faces) == 0:
                return []

            faces = self.app.get(frame)
            for face in faces:
                bbox = [int(max(0, v)) for v in face.bbox.tolist()]
                embedding = np.asarray(face.embedding, dtype=np.float32)
                results.append({'bbox': bbox, 'embedding': embedding})
            return results

        faces = self.app.get(frame)
        for face in faces:
            bbox = [int(max(0, v)) for v in face.bbox.tolist()]
            embedding = np.asarray(face.embedding, dtype=np.float32)
            results.append({'bbox': bbox, 'embedding': embedding})
        return results
