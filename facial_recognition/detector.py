from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
import os
import urllib.request
import urllib.error
import time
import logging

import cv2
import numpy as np
import onnxruntime as ort

from insightface.app import FaceAnalysis  # type: ignore[reportMissingTypeStubs]
from insightface.app.common import Face

class InsightFaceDetector:
    def __init__(
        self,
        use_gpu: bool,
        det_size: Tuple[int, int],
        model_name: str = 'buffalo_s',
        fast_detector: bool = False,
        cascade_path: Optional[str] = None,
    ) -> None:
        self.use_fast_detector = fast_detector
        self.det_size = det_size
        self.model_name = model_name
        providers = ['CUDAExecutionProvider'] if use_gpu else ['CPUExecutionProvider']

        import multiprocessing
        import onnxruntime as ort
        
        try:
            import psutil
            physical_cores = psutil.cpu_count(logical=False)
            if physical_cores is None:
                raise ValueError("psutil returned None for physical cores")
            method = "psutil.cpu_count"
        except Exception:
            physical_cores = max(1, multiprocessing.cpu_count() // 2)
            method = "multiprocessing.cpu_count() // 2 (fallback)"

        threads = min(4, max(1, physical_cores - 1))
        logging.getLogger(__name__).info(
            "Initializing ONNX Runtime with %d intra-op threads (Physical cores detected: %d via %s)",
            threads, physical_cores, method
        )

        _orig_init = ort.InferenceSession.__init__
        try:
            def _optimized_init(self, path_or_bytes, sess_options=None, providers=None, provider_options=None, **kwargs):
                if sess_options is None:
                    sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = threads
                sess_options.inter_op_num_threads = 1
                _orig_init(self, path_or_bytes, sess_options, providers, provider_options, **kwargs)
            
            ort.InferenceSession.__init__ = _optimized_init
            
            self.app: Any = FaceAnalysis(name=model_name, providers=providers, allowed_modules=['detection', 'recognition'])
            self.app.prepare(ctx_id=0 if use_gpu else -1, det_size=det_size)
        finally:
            ort.InferenceSession.__init__ = _orig_init

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

            for x, y, w, h in faces:
                x0 = int(x / scale_factor)
                y0 = int(y / scale_factor)
                x1 = int((x + w) / scale_factor)
                y1 = int((y + h) / scale_factor)
                x0 = max(0, x0)
                y0 = max(0, y0)
                x1 = min(frame.shape[1], x1)
                y1 = min(frame.shape[0], y1)
                results.append({'bbox': [x0, y0, x1, y1]})
            detect_dur = (time.perf_counter() - detect_start) * 1000.0
            logger.debug('Fast detect total %.2f ms', detect_dur)
            return results

        scrfd_start = time.perf_counter()
        bboxes, kpss = self.app.models['detection'].detect(frame, max_num=0, metric='default')
        if bboxes.shape[0] > 0:
            for i in range(bboxes.shape[0]):
                bbox = [int(max(0, v)) for v in bboxes[i, 0:4].tolist()]
                det_score = float(bboxes[i, 4])
                kps = kpss[i] if kpss is not None else None
                results.append({'bbox': bbox, 'det_score': det_score, 'kps': kps})
        scrfd_dur = (time.perf_counter() - scrfd_start) * 1000.0
        logger.debug('SCRFD detected %d faces in %.2f ms', len(results), scrfd_dur)
        detect_dur = (time.perf_counter() - detect_start) * 1000.0
        logger.debug('Full detect total %.2f ms', detect_dur)
        return results

    def extract_embedding(self, frame: np.ndarray, face_dict: Dict[str, Any]) -> Optional[np.ndarray]:
        if self.use_fast_detector and self.rec_model is not None:
            bbox = face_dict['bbox']
            x0, y0, x1, y1 = [int(v) for v in bbox]
            crop = frame[max(0, y0):min(frame.shape[0], y1), max(0, x0):min(frame.shape[1], x1)]
            if crop.size == 0:
                return None
            aligned = cv2.resize(crop, (self.rec_input_size, self.rec_input_size))
            return np.asarray(self.rec_model.get_feat(aligned), dtype=np.float32).flatten()

        if 'recognition' not in self.app.models:
            return None
        face = Face(bbox=np.array(face_dict['bbox']), kps=face_dict.get('kps'))
        self.app.models['recognition'].get(frame, face)
        if face.embedding is None:
            return None
        return np.asarray(face.embedding, dtype=np.float32)
