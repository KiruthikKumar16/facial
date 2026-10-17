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
from insightface.app.common import Face

ARCFACE_REFERENCE_LANDMARKS_112 = np.array([
    [38.2946, 51.6963],  # left eye
    [73.5318, 51.5014],  # right eye
    [56.0252, 71.7366],  # nose tip
    [41.5493, 92.3655],  # left mouth corner
    [70.7299, 92.2041],  # right mouth corner
], dtype=np.float32)


def enhance_cctv_illumination(img: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    """
    Universal CCTV Illumination & Shadow Normalizer.
    Mitigates ceiling spotlight shadows, window backlight, and underexposure
    by applying CLAHE on the luminance channel in LAB color space.
    """
    if img is None or img.size == 0:
        return img
    try:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(4, 4))
        cl = clahe.apply(l)
        enhanced_lab = cv2.merge((cl, a, b))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    except Exception:
        return img


def align_face_crop(
    frame: np.ndarray,
    bbox: List[int],
    kps: Optional[np.ndarray] = None,
    target_size: Tuple[int, int] = (112, 112),
    normalize_illumination: bool = True,
) -> Optional[np.ndarray]:
    """
    Perform 5-point landmark similarity transformation face alignment (ArcFace standard),
    or aspect-preserving squared crop if landmarks are unavailable.
    Applies universal CCTV illumination enhancement to normalize harsh overhead shadows.
    """
    aligned: Optional[np.ndarray] = None
    if kps is not None and len(kps) == 5:
        try:
            kps_arr = np.asarray(kps, dtype=np.float32)
            ref_pts = ARCFACE_REFERENCE_LANDMARKS_112
            if target_size != (112, 112):
                scale_x = target_size[0] / 112.0
                scale_y = target_size[1] / 112.0
                ref_pts = ref_pts * np.array([scale_x, scale_y], dtype=np.float32)
            M, _ = cv2.estimateAffinePartial2D(kps_arr, ref_pts)
            if M is not None:
                aligned = cv2.warpAffine(frame, M, target_size, borderValue=0.0)
        except Exception as e:
            logging.getLogger(__name__).debug("5-point landmark alignment failed: %s", e)

    if aligned is None:
        # Fallback: Aspect-ratio preserving square crop with 15% margin
        x0, y0, x1, y1 = [int(v) for v in bbox]
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            return None

        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        side = max(w, h) * 1.15
        half = side / 2.0

        sq_x0 = int(round(cx - half))
        sq_y0 = int(round(cy - half))
        sq_x1 = int(round(cx + half))
        sq_y1 = int(round(cy + half))

        pad_top = max(0, -sq_y0)
        pad_left = max(0, -sq_x0)
        pad_bottom = max(0, sq_y1 - frame.shape[0])
        pad_right = max(0, sq_x1 - frame.shape[1])

        crop_y0 = max(0, sq_y0)
        crop_y1 = min(frame.shape[0], sq_y1)
        crop_x0 = max(0, sq_x0)
        crop_x1 = min(frame.shape[1], sq_x1)

        crop = frame[crop_y0:crop_y1, crop_x0:crop_x1]
        if crop.size == 0:
            return None

        if pad_top > 0 or pad_bottom > 0 or pad_left > 0 or pad_right > 0:
            crop = cv2.copyMakeBorder(crop, pad_top, pad_bottom, pad_left, pad_right, cv2.BORDER_CONSTANT, value=[0, 0, 0])

        aligned = cv2.resize(crop, target_size, interpolation=cv2.INTER_LINEAR)

    if aligned is not None and normalize_illumination:
        aligned = enhance_cctv_illumination(aligned)

    return aligned


def estimate_face_pose_and_quality(
    bbox: List[int],
    kps: Optional[np.ndarray] = None,
    det_score: float = 0.5,
) -> Dict[str, Any]:
    """
    Universal CCTV 5-Point Landmark Geometric Pose & Quality Estimator.
    Works across any camera angle, ceiling height, distance, or lens distortion:
    1. pitch_ratio: Vertical eye-to-mouth ratio relative to interocular distance.
       - Direct frontal: ~0.85
       - Normal head tilt: 0.50 - 1.20
       - Downward desk viewing: 0.30 - 0.50
       - Extreme top-of-head / blind scalp: < 0.28 or nose <= eye line.
    2. yaw_ratio: Horizontal landmark symmetry around nose tip (1.0 = direct frontal).
    3. roll_angle: In-plane tilt angle in degrees.
    4. forehead_ratio: Forehead proportion of bounding box (high in downward ceiling CCTV).
    5. is_steep_scalp: Flag indicating a blind scalp view lacking identifiable frontal facial geometry.
    6. pose_quality: Normalized 0.0 - 1.0 composite confidence for embedding & clustering.
    """
    x0, y0, x1, y1 = [int(v) for v in bbox]
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)

    if kps is None or len(kps) != 5:
        res_factor = min(1.0, max(0.1, min(w, h) / 60.0))
        return {
            "pitch_ratio": 0.75,
            "yaw_ratio": 0.75,
            "roll_angle": 0.0,
            "forehead_ratio": 0.40,
            "is_steep_scalp": False,
            "pose_quality": round(float(det_score * res_factor * 0.6), 3),
        }

    kps_arr = np.asarray(kps, dtype=np.float32)
    left_eye = kps_arr[0]
    right_eye = kps_arr[1]
    nose = kps_arr[2]
    left_mouth = kps_arr[3]
    right_mouth = kps_arr[4]

    # Inter-ocular distance & roll angle
    eye_dx = float(right_eye[0] - left_eye[0])
    eye_dy = float(right_eye[1] - left_eye[1])
    eye_dist = max(1.0, float(np.sqrt(eye_dx * eye_dx + eye_dy * eye_dy)))
    roll_angle = float(np.degrees(np.arctan2(eye_dy, eye_dx)))

    # Pitch calculation (vertical eye-to-mouth distance)
    eye_y_avg = float(left_eye[1] + right_eye[1]) / 2.0
    mouth_y_avg = float(left_mouth[1] + right_mouth[1]) / 2.0
    vertical_span = mouth_y_avg - eye_y_avg
    pitch_ratio = float(vertical_span / eye_dist)

    # Forehead ratio in bounding box
    forehead_ratio = float(max(0.0, eye_y_avg - y0) / h)

    # Yaw symmetry around nose tip
    left_to_nose = abs(float(nose[0] - left_eye[0]))
    right_to_nose = abs(float(right_eye[0] - nose[0]))
    min_dist = min(left_to_nose, right_to_nose)
    max_dist = max(left_to_nose, right_to_nose)
    yaw_ratio = float(min_dist / (max_dist + 1e-4))

    # Detect blind overhead scalp (no eyes/nose geometry visible)
    is_steep_scalp = (pitch_ratio < 0.28) or (forehead_ratio > 0.68 and pitch_ratio < 0.40) or (float(nose[1]) <= eye_y_avg)

    # Composite pose quality score [0.0 - 1.0]
    pitch_score = max(0.0, min(1.0, 1.0 - abs(pitch_ratio - 0.85) / 0.70))
    yaw_score = max(0.0, min(1.0, yaw_ratio))
    roll_score = max(0.0, min(1.0, 1.0 - abs(roll_angle) / 45.0))
    res_score = min(1.0, max(0.1, min(w, h) / 70.0))

    if is_steep_scalp:
        pose_quality = 0.15 * det_score
    else:
        pose_quality = (pitch_score * 0.40 + yaw_score * 0.30 + roll_score * 0.10 + res_score * 0.20) * det_score

    return {
        "pitch_ratio": round(pitch_ratio, 3),
        "yaw_ratio": round(yaw_ratio, 3),
        "roll_angle": round(roll_angle, 1),
        "forehead_ratio": round(forehead_ratio, 3),
        "is_steep_scalp": bool(is_steep_scalp),
        "pose_quality": round(float(pose_quality), 3),
    }


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
            
            self.app: Any = FaceAnalysis(name=model_name, providers=providers, allowed_modules=['detection', 'recognition', 'genderage'])
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

    def detect(
        self,
        frame: np.ndarray,
        min_score: float = 0.52,
        min_size: int = 44,
    ) -> List[Dict[str, Any]]:
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
                logger.exception("Haar cascade error")
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
                if (x1 - x0) >= min_size and (y1 - y0) >= min_size:
                    results.append({'bbox': [x0, y0, x1, y1]})
            detect_dur = (time.perf_counter() - detect_start) * 1000.0
            logger.debug('Fast detect total %.2f ms', detect_dur)
            return results

        scrfd_start = time.perf_counter()
        bboxes, kpss = self.app.models['detection'].detect(frame, max_num=0, metric='default')
        if bboxes.shape[0] > 0:
            for i in range(bboxes.shape[0]):
                bbox = [int(max(0, v)) for v in bboxes[i, 0:4].tolist()]
                det_score = float(bboxes[i, 4]) if bboxes.shape[1] > 4 else 0.5
                if det_score < min_score:
                    continue
                w = max(0, bbox[2] - bbox[0])
                h = max(0, bbox[3] - bbox[1])
                if w < min_size or h < min_size:
                    continue
                kps = kpss[i] if kpss is not None else None
                pose_meta = estimate_face_pose_and_quality(bbox, kps, det_score=det_score)
                if pose_meta['is_steep_scalp'] and det_score < 0.65:
                    continue
                results.append({
                    'bbox': bbox,
                    'det_score': det_score,
                    'kps': kps,
                    'pose_quality': pose_meta['pose_quality'],
                    'is_steep_scalp': pose_meta['is_steep_scalp'],
                    'pose_meta': pose_meta,
                })
        scrfd_dur = (time.perf_counter() - scrfd_start) * 1000.0
        logger.debug('SCRFD detected %d faces in %.2f ms', len(results), scrfd_dur)
        detect_dur = (time.perf_counter() - detect_start) * 1000.0
        logger.debug('Full detect total %.2f ms', detect_dur)
        return results

    def extract_embedding(self, frame: np.ndarray, face_dict: Dict[str, Any]) -> Optional[np.ndarray]:
        if self.use_fast_detector and self.rec_model is not None:
            aligned = align_face_crop(
                frame,
                face_dict['bbox'],
                kps=face_dict.get('kps'),
                target_size=(self.rec_input_size, self.rec_input_size),
            )
            if aligned is None or aligned.size == 0:
                return None
            return np.asarray(self.rec_model.get_feat(aligned), dtype=np.float32).flatten()

        if 'recognition' not in self.app.models:
            return None

        bbox = face_dict['bbox']
        kps = face_dict.get('kps')
        if kps is None:
            x0, y0, x1, y1 = [int(v) for v in bbox]
            w, h = x1 - x0, y1 - y0
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            side = max(w, h)
            half = side / 2.0
            bbox = [
                int(max(0, cx - half)),
                int(max(0, cy - half)),
                int(min(frame.shape[1], cx + half)),
                int(min(frame.shape[0], cy + half)),
            ]

        face = Face(bbox=np.array(bbox), kps=kps)
        
        if 'genderage' in self.app.models:
            self.app.models['genderage'].get(frame, face)
            if hasattr(face, 'sex') and face.sex is not None:
                face_dict['gender'] = "male" if face.sex == "M" else "female" if face.sex == "F" else "unknown"
            if hasattr(face, 'age') and face.age is not None:
                face_dict['age'] = int(face.age)
                
        self.app.models['recognition'].get(frame, face)
        if face.embedding is None:
            return None
        return np.asarray(face.embedding, dtype=np.float32)
