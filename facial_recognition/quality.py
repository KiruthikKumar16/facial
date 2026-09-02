import cv2
import numpy as np
import math
from typing import Dict, Any, Tuple, Optional, List

class QualityCategory:
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    POOR = "POOR"

class FaceQualityAssessor:
    """
    Measurable face and image quality assessment engine.
    Calculates granular metrics and categorizes detected faces into HIGH, MEDIUM, or POOR quality.
    """
    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        """
        Initialize assessor with configurable thresholds.
        """
        thresholds = thresholds or {}
        self.t_high = thresholds.get('high', {
            'min_size': 80,
            'min_confidence': 0.7,
            'min_sharpness': 100.0,
            'illumination_range': [40, 210],
            'min_pose_score': 0.65,
            'min_occlusion_score': 0.60
        })
        self.t_medium = thresholds.get('medium', {
            'min_size': 40,
            'min_confidence': 0.4,
            'min_sharpness': 50.0,
            'illumination_range': [20, 235],
            'min_pose_score': 0.40,
            'min_occlusion_score': 0.35
        })
        self.temporal_observations_required = thresholds.get('temporal_observations_required', 5)

    def assess(
        self, 
        frame: np.ndarray, 
        face_dict: Dict[str, Any], 
        prev_bbox: Optional[List[int]] = None,
        dt: float = 0.033
    ) -> Tuple[str, Dict[str, float]]:
        """
        Assess face quality across multiple orthogonal dimensions:
        - blur / sharpness (Laplacian variance)
        - face size (spatial resolution)
        - pose (yaw symmetry, pitch, roll from 5-point landmarks)
        - illumination (mean luminance and contrast)
        - occlusion (quadrant symmetry and intensity balance)
        - detection confidence (SCRFD score)
        - motion (spatial displacement velocity)
        
        Returns:
            (category, metrics_dict)
        """
        bbox = face_dict.get('bbox', [0, 0, 0, 0])
        confidence = float(face_dict.get('det_score', 1.0))
        kps = face_dict.get('kps', None)

        fh, fw = frame.shape[:2]
        x0, y0, x1, y1 = [int(v) for v in bbox]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(fw, x1), min(fh, y1)

        w = max(0, x1 - x0)
        h = max(0, y1 - y0)
        size = float(min(w, h))

        # Default metrics
        metrics: Dict[str, float] = {
            'size': size,
            'confidence': confidence,
            'sharpness': 0.0,
            'illumination': 0.0,
            'contrast': 0.0,
            'pose_score': 1.0,
            'occlusion_score': 1.0,
            'motion_score': 1.0,
            'yaw_symmetry': 1.0,
            'roll_angle': 0.0,
        }

        if w >= 5 and h >= 5:
            crop = frame[y0:y1, x0:x1]
            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            # 1. Blur / Sharpness (Variance of Laplacian)
            metrics['sharpness'] = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())

            # 2. Illumination & Contrast
            mean_lum = float(np.mean(gray_crop))
            std_lum = float(np.std(gray_crop))
            metrics['illumination'] = mean_lum
            metrics['contrast'] = std_lum

            # 3. Occlusion Assessment (Upper vs Lower / Left vs Right contrast balance)
            metrics['occlusion_score'] = self._compute_occlusion_score(gray_crop)

            # 4. Pose Assessment (from landmarks if available)
            if kps is not None and len(kps) >= 5:
                pose_s, yaw_sym, roll_deg = self._compute_pose_metrics(kps, bbox)
                metrics['pose_score'] = pose_s
                metrics['yaw_symmetry'] = yaw_sym
                metrics['roll_angle'] = roll_deg

            # 5. Motion Score (based on bbox displacement between frames)
            if prev_bbox is not None:
                metrics['motion_score'] = self._compute_motion_score(bbox, prev_bbox, dt)

        # Categorize
        category = self._categorize(metrics)
        metrics['score'] = self._compute_aggregate_score(metrics)

        return category, metrics

    def _compute_pose_metrics(self, kps: Any, bbox: List[int]) -> Tuple[float, float, float]:
        """
        Compute pose score from 5 InsightFace facial landmarks:
        [0]=left eye, [1]=right eye, [2]=nose, [3]=left mouth, [4]=right mouth.
        """
        try:
            kps_arr = np.array(kps, dtype=np.float32)
            le, re, nose, lm, rm = kps_arr[0], kps_arr[1], kps_arr[2], kps_arr[3], kps_arr[4]

            # Roll (in-plane tilt)
            dx = re[0] - le[0]
            dy = re[1] - le[1]
            roll_rad = math.atan2(dy, dx) if dx != 0 else 0.0
            roll_deg = abs(math.degrees(roll_rad))
            roll_score = max(0.0, 1.0 - (roll_deg / 45.0))

            # Yaw (symmetry of nose relative to left and right eyes)
            d_left = abs(nose[0] - le[0])
            d_right = abs(re[0] - nose[0])
            total_eye_dist = d_left + d_right
            if total_eye_dist > 1e-4:
                yaw_ratio = abs(d_left - d_right) / total_eye_dist
                yaw_symmetry = max(0.0, 1.0 - (yaw_ratio * 1.5))
            else:
                yaw_symmetry = 0.5

            # Pitch (vertical symmetry between eye midpoint, nose, and mouth midpoint)
            eye_mid_y = (le[1] + re[1]) / 2.0
            mouth_mid_y = (lm[1] + rm[1]) / 2.0
            upper_h = abs(nose[1] - eye_mid_y)
            lower_h = abs(mouth_mid_y - nose[1])
            total_h = upper_h + lower_h
            if total_h > 1e-4:
                pitch_ratio = abs(upper_h - lower_h) / total_h
                pitch_score = max(0.0, 1.0 - (pitch_ratio * 1.2))
            else:
                pitch_score = 0.5

            pose_score = (yaw_symmetry * 0.5) + (roll_score * 0.25) + (pitch_score * 0.25)
            return float(np.clip(pose_score, 0.0, 1.0)), float(yaw_symmetry), float(roll_deg)
        except Exception:
            return 0.5, 0.5, 0.0

    def _compute_occlusion_score(self, gray_crop: np.ndarray) -> float:
        """
        Assess occlusion likelihood by checking quadrant symmetry and lower-face texture.
        """
        gh, gw = gray_crop.shape
        if gh < 10 or gw < 10:
            return 0.5

        # Split into quadrants
        top_half = gray_crop[:gh//2, :]
        bot_half = gray_crop[gh//2:, :]

        top_std = float(np.std(top_half))
        bot_std = float(np.std(bot_half))

        # Complete mask often crushes bottom half variance to near zero relative to top
        if top_std > 5.0 and bot_std < 3.0:
            return 0.3

        # Left vs Right symmetry
        left_half = gray_crop[:, :gw//2]
        right_half = gray_crop[:, gw//2:]
        left_mean = float(np.mean(left_half))
        right_mean = float(np.mean(right_half))

        asym = abs(left_mean - right_mean) / max(1.0, (left_mean + right_mean) / 2.0)
        occlusion_score = max(0.0, 1.0 - asym)
        return float(np.clip(occlusion_score, 0.0, 1.0))

    def _compute_motion_score(self, bbox: List[int], prev_bbox: List[int], dt: float) -> float:
        """
        Compute motion stability score based on bbox velocity.
        """
        c_x = (bbox[0] + bbox[2]) / 2.0
        c_y = (bbox[1] + bbox[3]) / 2.0
        p_x = (prev_bbox[0] + prev_bbox[2]) / 2.0
        p_y = (prev_bbox[1] + prev_bbox[3]) / 2.0

        disp = math.sqrt((c_x - p_x)**2 + (c_y - p_y)**2)
        velocity = disp / max(1e-4, dt) # pixels per second

        # Velocity > 400 px/s penalizes score
        motion_score = max(0.0, 1.0 - (velocity / 500.0))
        return float(np.clip(motion_score, 0.0, 1.0))

    def _categorize(self, m: Dict[str, float]) -> str:
        """
        Categorize face into HIGH, MEDIUM, or POOR.
        """
        th = self.t_high
        if (m['size'] >= th.get('min_size', 80) and 
            m['confidence'] >= th.get('min_confidence', 0.7) and
            m['sharpness'] >= th.get('min_sharpness', 100.0) and
            th.get('illumination_range', [40, 210])[0] <= m['illumination'] <= th.get('illumination_range', [40, 210])[1] and
            m.get('pose_score', 1.0) >= th.get('min_pose_score', 0.65) and
            m.get('occlusion_score', 1.0) >= th.get('min_occlusion_score', 0.60)):
            return QualityCategory.HIGH

        tm = self.t_medium
        if (m['size'] >= tm.get('min_size', 40) and 
            m['confidence'] >= tm.get('min_confidence', 0.4) and
            m['sharpness'] >= tm.get('min_sharpness', 50.0) and
            tm.get('illumination_range', [20, 235])[0] <= m['illumination'] <= tm.get('illumination_range', [20, 235])[1] and
            m.get('pose_score', 1.0) >= tm.get('min_pose_score', 0.40) and
            m.get('occlusion_score', 1.0) >= tm.get('min_occlusion_score', 0.35)):
            return QualityCategory.MEDIUM

        return QualityCategory.POOR

    def _compute_aggregate_score(self, m: Dict[str, float]) -> float:
        """
        Compute an aggregate 0-100 quality score for logging and forensic analysis.
        """
        s_size = min(100.0, max(0.0, (m['size'] - 20) / 100.0 * 100.0))
        s_conf = min(100.0, max(0.0, m['confidence'] * 100.0))
        s_sharp = min(100.0, max(0.0, m['sharpness'] / 3.0))

        ill = m['illumination']
        if 60 <= ill <= 180:
            s_ill = 100.0
        else:
            dist = min(abs(ill - 60), abs(ill - 180))
            s_ill = max(0.0, 100.0 - (dist * 1.5))

        s_pose = m.get('pose_score', 1.0) * 100.0
        s_occl = m.get('occlusion_score', 1.0) * 100.0
        s_motion = m.get('motion_score', 1.0) * 100.0

        aggregate = (
            s_size * 0.20 +
            s_conf * 0.20 +
            s_sharp * 0.20 +
            s_ill * 0.15 +
            s_pose * 0.10 +
            s_occl * 0.10 +
            s_motion * 0.05
        )
        return float(round(np.clip(aggregate, 0.0, 100.0), 2))

