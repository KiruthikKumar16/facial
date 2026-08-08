from typing import List, Tuple

import cv2
import numpy as np
from insightface.app import FaceAnalysis


class InsightFaceDetector:
    def __init__(self, use_gpu: bool, det_size: Tuple[int, int], model_name: str = 'buffalo_l', fast_detector: bool = False) -> None:
        self.use_fast_detector = fast_detector
        self.det_size = det_size
        self.model_name = model_name
        providers = ['CUDAExecutionProvider'] if use_gpu else ['CPUExecutionProvider']

        self.app = FaceAnalysis(name=model_name, providers=providers)
        self.app.prepare(ctx_id=0 if use_gpu else -1, det_size=det_size)

        self.use_fast_detector = self.use_fast_detector and hasattr(cv2, 'CascadeClassifier') and hasattr(cv2, 'data')
        if self.use_fast_detector:
            self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def detect(self, frame: np.ndarray) -> List[dict]:
        results: List[dict] = []
        if self.use_fast_detector:
            # Do a fast face detection on a small grayscale image, then embed the cropped face.
            scale_factor = 320 / max(frame.shape[:2])
            small = cv2.resize(frame, (0, 0), fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_LINEAR)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
            for x, y, w, h in faces:
                x0 = int(x / scale_factor)
                y0 = int(y / scale_factor)
                x1 = int((x + w) / scale_factor)
                y1 = int((y + h) / scale_factor)
                x0 = max(0, x0)
                y0 = max(0, y0)
                x1 = min(frame.shape[1], x1)
                y1 = min(frame.shape[0], y1)
                crop = frame[y0:y1, x0:x1]
                if crop.size == 0:
                    continue
                faces_in_crop = self.app.get(crop)
                if not faces_in_crop:
                    continue
                face = faces_in_crop[0]
                bbox = [x0, y0, x1, y1]
                embedding = np.asarray(face.embedding, dtype=np.float32)
                results.append({'bbox': bbox, 'embedding': embedding})
            return results

        faces = self.app.get(frame)
        for face in faces:
            bbox = [int(max(0, v)) for v in face.bbox.tolist()]
            embedding = np.asarray(face.embedding, dtype=np.float32)
            results.append({'bbox': bbox, 'embedding': embedding})
        return results
