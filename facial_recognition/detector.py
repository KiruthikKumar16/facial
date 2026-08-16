from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
import os
import urllib.request
import urllib.error
import time
import logging

import cv2
import numpy as np
from insightface.app import FaceAnalysis  # type: ignore[reportMissingTypeStubs]


class InsightFaceDetector:
    def __init__(
        self,
        use_gpu: bool,
        det_size: Tuple[int, int],
        model_name: str = 'buffalo_l',
        fast_detector: bool = False,
        cascade_path: Optional[str] = None,
    ) -> None:
        self.use_fast_detector = fast_detector
        self.det_size = det_size
        self.model_name = model_name
        providers = ['CUDAExecutionProvider'] if use_gpu else ['CPUExecutionProvider']

        self.app: Any = FaceAnalysis(name=model_name, providers=providers)
        self.app.prepare(ctx_id=0 if use_gpu else -1, det_size=det_size)

        cv2_any: Any = cv2
        self.use_fast_detector = self.use_fast_detector and hasattr(cv2_any, 'CascadeClassifier')
        self.cascade: Optional[Any] = None
        self.rec_model: Optional[Any] = None
        self.rec_input_size = 112

        if self.use_fast_detector:
            repo_cascade_path = Path(__file__).resolve().parent.parent / 'cascades' / 'haarcascade_frontalface_default.xml'
            if cascade_path is None and repo_cascade_path.exists():
                cascade_path = str(repo_cascade_path)

            if cascade_path is None:
                cascade_path = str(Path(cv2_any.data.haarcascades) / 'haarcascade_frontalface_default.xml')

            logger = logging.getLogger(__name__)
            if not os.path.exists(cascade_path):
                if repo_cascade_path.parent.exists() or repo_cascade_path.parent.mkdir(parents=True, exist_ok=True):
                    try:
                        logger.info('Downloading Haar cascade to %s', repo_cascade_path)
                        urllib.request.urlretrieve(
                            'https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml',
                            repo_cascade_path,
                        )
                        cascade_path = str(repo_cascade_path)
                        logger.info('Downloaded Haar cascade to %s', repo_cascade_path)
                    except urllib.error.URLError as e:
                        logger.warning('Could not download Haar cascade: %s; disabling fast detector.', e)
                        self.use_fast_detector = False
                        return

            if not os.path.exists(cascade_path):
                logging.getLogger(__name__).warning(
                    'Haar cascade file not found at %s; disabling fast detector.', cascade_path
                )
                self.use_fast_detector = False
                return

            self.cascade = cv2_any.CascadeClassifier(cascade_path)
            if self.cascade is None or self.cascade.empty():
                logging.getLogger(__name__).warning('Could not load Haar cascade at %s; disabling fast detector.', cascade_path)
                self.use_fast_detector = False
                self.cascade = None
                return

            self.rec_model = cast(Dict[str, Any], self.app.models).get('recognition')
            if self.rec_model is not None and hasattr(self.rec_model, 'input_size'):
                self.rec_input_size = int(self.rec_model.input_size[0])
            else:
                logging.getLogger(__name__).warning('Recognition model unavailable; disabling fast detector.')
                self.use_fast_detector = False
                self.cascade = None
                self.rec_model = None

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        logger = logging.getLogger(__name__)
        detect_start = time.perf_counter()
        if self.use_fast_detector and self.cascade is not None and self.rec_model is not None:
            haar_start = time.perf_counter()
            scale_factor = 320 / max(frame.shape[:2])
            small = cv2.resize(frame, (0, 0), fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_LINEAR)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            try:
                faces = cast(List[Any], self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)))
            except Exception:
                faces = []
            haar_dur = (time.perf_counter() - haar_start) * 1000.0
            logger.debug('Haar found %d candidates in %.2f ms', len(faces), haar_dur)

            emb_start = time.perf_counter()
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
                aligned = cv2.resize(crop, (self.rec_input_size, self.rec_input_size))
                embedding = np.asarray(self.rec_model.get_feat(aligned), dtype=np.float32).flatten()
                results.append({'bbox': [x0, y0, x1, y1], 'embedding': embedding})
            emb_dur = (time.perf_counter() - emb_start) * 1000.0
            logger.debug('Embedding extraction for %d faces took %.2f ms', len(results), emb_dur)
            detect_dur = (time.perf_counter() - detect_start) * 1000.0
            logger.debug('Fast detect total %.2f ms', detect_dur)
            return results

        scrfd_start = time.perf_counter()
        faces = self.app.get(frame)
        for face in faces:
            bbox = [int(max(0, v)) for v in face.bbox.tolist()]
            embedding = np.asarray(face.embedding, dtype=np.float32)
            results.append({'bbox': bbox, 'embedding': embedding})
        scrfd_dur = (time.perf_counter() - scrfd_start) * 1000.0
        logger.debug('SCRFD detected %d faces in %.2f ms', len(results), scrfd_dur)
        detect_dur = (time.perf_counter() - detect_start) * 1000.0
        logger.debug('Full detect total %.2f ms', detect_dur)
        return results
