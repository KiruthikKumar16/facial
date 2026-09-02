"""
CPU-only optimized runner for facial_recognition
- Limits OpenMP/MKL threads for onnxruntime / numpy
- Uses smaller det_size default (320x320)
- Skips frames (process every Nth frame)
- Minimal logging and efficient copying

Run: python main_cpu.py
"""
from pathlib import Path
import os
import signal
import threading
import time
from urllib.parse import quote
from typing import Any, Deque, Dict, List, Optional, Tuple, cast
import logging

try:
    from dotenv import load_dotenv, find_dotenv

    def _resolve_env_path() -> Path | None:
        here = Path(__file__).resolve().parent
        root_candidate = here.parent / ".env"
        if root_candidate.is_file():
            return root_candidate
        fallback = find_dotenv(usecwd=True)
        if fallback:
            return Path(fallback)
        return None

    _env = _resolve_env_path()
    if _env is not None:
        load_dotenv(_env, override=False)
except ImportError:
    pass

# bind thread limits early to help native libs
os.environ.setdefault('OMP_NUM_THREADS', os.environ.get('OMP_NUM_THREADS', '4'))
os.environ.setdefault('MKL_NUM_THREADS', os.environ.get('MKL_NUM_THREADS', '4'))
os.environ.setdefault('OPENBLAS_NUM_THREADS', os.environ.get('OPENBLAS_NUM_THREADS', '4'))

import cv2  # type: ignore[reportMissingTypeStubs]
import numpy as np
import yaml  # type: ignore[reportMissingTypeStubs]

cv2: Any = cv2
yaml: Any = yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)

from capture import CameraCapture
from detector import InsightFaceDetector  # type: ignore[reportMissingImports]
from logger import DetectionLogger
from recognizer import Recognizer
from pending import PendingSaver
from cli import parse_run_args, resolve_camera_size, resolve_det_size, resolve_model
from overlay import draw_text_block
from edge_stream import EdgeFramePublisher
from collections import deque


TIERS = {
    'fast': {'det_size': (320, 320), 'frame_skip': 3},
    'mid':  {'det_size': (256, 256), 'frame_skip': 5},
    'slow': {'det_size': (192, 192), 'frame_skip': 8},
}


class CpuCameraPipeline:
    def __init__(
        self,
        camera_id: str,
        source: Any,
        detector: Any,
        recognizer: Any,
        logger: Any,
        frame_size: Tuple[int, int] = (256, 256),
        frame_skip: int = 5,
        recognition_interval: int = 2,
        use_tracker: bool = True,
        pending_saver: Optional[PendingSaver] = None,
        cpu_tier: str = 'auto',
        capture_width: int = 640,
        capture_height: int = 480,
        lock_resolution: bool = False,
        model_name: str = 'buffalo_s',
        quality_assessor: Any = None,
        track_fusion_cfg: Optional[Dict[str, Any]] = None,
        camera_config_manager: Any = None,
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.detector = detector
        self.recognizer = recognizer
        self.logger = logger
        self.pending_saver = pending_saver
        self.frame_size = frame_size
        self.frame_skip = max(1, int(frame_skip))
        self.recognition_interval = float(recognition_interval)
        self.use_tracker = bool(use_tracker)
        self.quality_assessor = quality_assessor
        self.camera_config_manager = camera_config_manager
        from track_fusion import TemporalTrackManager
        
        # Apply camera-specific profile if available
        profile = None
        if self.camera_config_manager:
            profile = self.camera_config_manager.get_profile(self.camera_id)
            if profile:
                self.recognizer.threshold = profile.recognition_threshold
                if profile.sampling_rate > 1:
                    self.frame_skip = profile.sampling_rate

        # Temporal Track Fusion Manager
        track_cfg = track_fusion_cfg or {}
        temporal_win = profile.temporal_window if profile else float(track_cfg.get('max_observation_window_seconds', 3.0))
        sim_thresh = profile.recognition_threshold if profile else float(track_cfg.get('finalization_similarity_threshold', self.recognizer.threshold))

        self.track_manager = TemporalTrackManager(
            max_observation_window_seconds=temporal_win,
            max_observations_per_track=int(track_cfg.get('max_observations_per_track', 30)),
            min_observations_to_finalize=int(track_cfg.get('min_observations_to_finalize', 3)),
            similarity_threshold=sim_thresh,
            finalization_margin=float(track_cfg.get('finalization_margin', 0.05)),
            max_missed_frames=int(track_cfg.get('max_missed_frames', 15)),
            quality_weight_gamma=float(track_cfg.get('quality_weight_gamma', 2.0)),
            temporal_decay_lambda=float(track_cfg.get('temporal_decay_lambda', 0.1)),
            max_active_tracks=int(track_cfg.get('max_active_tracks', 50)),
        )
        self._frame_count = 0
        self._processed_count = 0
        self.latest_frame: Optional[Any] = None
        self.raw_frame: Optional[Any] = None
        self.lock = threading.Lock()
        
        self.last_detections: List[Dict[str, Any]] = []
        self.face_trackers: List[Any] = []
        self._tracker_warning_printed = False
        
        self._processed_ts: Deque[float] = deque()
        self.detector_fps = 0.0
        self._display_ts: Deque[float] = deque()
        self.display_fps = 0.0
        
        self.cpu_tier = cpu_tier
        self.lock_resolution = lock_resolution
        self.model_name = model_name
        self.capture_width = capture_width
        self.capture_height = capture_height
        self.current_tier_name = 'mid'
        self.calibrated_tier_name = 'mid'
        self.last_tier_shift_time = 0.0
        self._display_fps_history: Deque[float] = deque(maxlen=90)
        
        self.capture = CameraCapture(
            source,
            camera_id,
            self._capture_callback,
            reconnect_interval=10,
            capture_width=capture_width,
            capture_height=capture_height,
        )
        self.last_fps_time = None
        self.fps = 0.0

    def _run_calibration(self) -> None:
        if self.lock_resolution:
            self.current_tier_name = self.cpu_tier if self.cpu_tier != 'auto' else 'fixed'
            logger.info("[%s] Fixed detection resolution: %s (CLI override)", self.camera_id, self.frame_size)
            return

        if self.cpu_tier != 'auto' and self.cpu_tier in TIERS:
            self.calibrated_tier_name = self.cpu_tier
            self.current_tier_name = self.cpu_tier
            t = TIERS[self.cpu_tier]
            self.frame_size = t['det_size']
            self.frame_skip = t['frame_skip']
            logger.info("[%s] Manual tier override: %s", self.camera_id, self.cpu_tier)
            return

        logger.info("[%s] Running auto-calibration...", self.camera_id)
        latencies = []
        for _ in range(30):
            with self.lock:
                frame = self.raw_frame
            if frame is not None:
                small = cv2.resize(frame, (256, 256), interpolation=cv2.INTER_LINEAR)
                t0 = time.perf_counter()
                self.detector.detect(small)
                latencies.append((time.perf_counter() - t0) * 1000.0)
            time.sleep(0.05)
        
        if not latencies:
            logger.warning("[%s] Calibration failed (no frames). Defaulting to 'mid' tier.", self.camera_id)
            return

        median_latency = float(np.median(latencies))
        if median_latency < 15.0:
            tier = 'fast'
        elif median_latency < 30.0:
            tier = 'mid'
        else:
            tier = 'slow'

        self.calibrated_tier_name = tier
        self.current_tier_name = tier
        t = TIERS[tier]
        self.frame_size = t['det_size']
        self.frame_skip = t['frame_skip']
        logger.info("[%s] Calibration complete. Median latency: %.1f ms -> Selected tier: %s", self.camera_id, median_latency, tier)

    def start(self):
        logger.info('Starting CameraPipeline %s (source=%s)', self.camera_id, self.source)
        self.capture.start()
        # Wait for first frame
        for _ in range(50):
            with self.lock:
                if self.raw_frame is not None:
                    break
            time.sleep(0.1)
        self._run_calibration()

    def stop(self):
        logger.info('Stopping CameraPipeline %s', self.camera_id)
        self.capture.stop()
        self.capture.join(timeout=5)

    def _capture_callback(self, camera_id: str, frame: Any) -> None:
        with self.lock:
            self.raw_frame = frame

    def _create_tracker(self) -> Optional[Any]:
        try:
            return cv2.TrackerKCF_create()
        except AttributeError:
            try:
                if hasattr(cv2, 'legacy') and hasattr(cv2.legacy, 'TrackerKCF_create'):
                    return cv2.legacy.TrackerKCF_create()
                if hasattr(cv2, 'TrackerMOSSE_create'):
                    return cv2.TrackerMOSSE_create()
            except Exception:
                pass
        return None

    def _init_trackers(self, frame: Any) -> None:
        self.face_trackers = []
        if not self.use_tracker or not self.last_detections:
            return

        for det in self.last_detections:
            tracker = self._create_tracker()
            if tracker is None:
                if self.use_tracker and not self._tracker_warning_printed:
                    print("Warning: OpenCV tracker unavailable. Install opencv-contrib-python.")
                    self._tracker_warning_printed = True
                self.use_tracker = False
                self.face_trackers = []
                return
            l, t, r, b = det['bbox']
            w, h = max(1, r - l), max(1, b - t)
            try:
                ok = tracker.init(frame, (l, t, w, h))
            except Exception:
                ok = False
            if not ok:
                self.face_trackers = []
                return
            self.face_trackers.append(tracker)

    def _update_tracked_boxes(self, frame: Any) -> bool:
        if not self.face_trackers or len(self.face_trackers) != len(self.last_detections):
            return False
        for tracker, det in zip(self.face_trackers, self.last_detections):
            ok, box = tracker.update(frame)
            if not ok:
                self.face_trackers = []
                return False
            x, y, w, h = box
            x0 = int(max(0, x))
            y0 = int(max(0, y))
            x1 = int(min(frame.shape[1] - 1, x0 + max(1, int(w))))
            y1 = int(min(frame.shape[0] - 1, y0 + max(1, int(h))))
            det['bbox'] = (x0, y0, x1, y1)
        return True

    def _compute_iou(self, boxA, boxB):
        xA, yA = max(boxA[0], boxB[0]), max(boxA[1], boxB[1])
        xB, yB = min(boxA[2], boxB[2]), min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0: return 0.0
        return interArea / float((boxA[2]-boxA[0])*(boxA[3]-boxA[1]) + (boxB[2]-boxB[0])*(boxB[3]-boxB[1]) - interArea)

    def step(self) -> Optional[Any]:
        with self.lock:
            if self.raw_frame is None:
                return self.latest_frame
            frame = self.raw_frame
            self.raw_frame = None

        now = time.time()
        if self.last_fps_time is not None:
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(now - self.last_fps_time, 1e-6))
        self.last_fps_time = now

        self._frame_count += 1
        
        trackers_valid = False
        if self.last_detections and self.face_trackers:
            trackers_valid = self._update_tracked_boxes(frame)

        run_det = False
        if (self._frame_count % self.frame_skip) == 0:
            run_det = True
        if not trackers_valid and self.last_detections:
            run_det = True
            
        if run_det:
            self._processed_count += 1
            small = cv2.resize(frame, self.frame_size, interpolation=cv2.INTER_LINEAR)
            det_start = time.perf_counter()
            detections = self.detector.detect(small)
            
            fh, fw = frame.shape[:2]
            sh, sw = small.shape[:2]
            x_scale = fw / sw
            y_scale = fh / sh
            
            frame_observations = []
            from track_fusion import FaceObservation
            
            for face in detections:
                l, t, r, b = face['bbox']
                l, r = int(l * x_scale), int(r * x_scale)
                t, b = int(t * y_scale), int(b * y_scale)
                face['bbox'] = [l, t, r, b]
                
                if 'kps' in face and face['kps'] is not None:
                    kps = np.array(face['kps'], dtype=np.float32)
                    kps[:, 0] *= x_scale
                    kps[:, 1] *= y_scale
                    face['kps'] = kps
                
                quality_category = "HIGH"
                quality_score = 100.0
                dt = max(0.001, now - (self.last_fps_time or now))

                if self.quality_assessor:
                    cat, q_metrics = self.quality_assessor.assess(frame, face, dt=dt)
                    quality_category = cat
                    quality_score = q_metrics.get('score', 100.0)

                emb = None
                if quality_category != "POOR":
                    emb = self.detector.extract_embedding(frame, face)

                obs = FaceObservation(
                    timestamp=now,
                    bbox=[l, t, r, b],
                    quality_score=quality_score,
                    quality_category=quality_category,
                    confidence=float(face.get('det_score', 1.0)),
                    embedding=emb,
                )
                frame_observations.append(obs)

            track_pairs = self.track_manager.process_frame_observations(
                frame_observations,
                self.recognizer.labels,
                self.recognizer.embeddings,
                current_time=now,
            )

            new_detections = []
            for track, obs in track_pairs:
                full_bbox = obs.bbox
                track_id = track.track_id
                fused_id = track.fused_identity
                fused_conf = track.fused_confidence
                is_finalized = track.is_finalized

                if is_finalized:
                    label = f"[{track_id}] {fused_id}*"
                    if self.logger is not None:
                        cfg_ver = 1
                        if self.camera_config_manager:
                            prof = self.camera_config_manager.get_profile(self.camera_id)
                            if prof:
                                cfg_ver = prof.version
                        self.logger.log_detection(
                            self.camera_id, 
                            full_bbox, 
                            fused_id, 
                            float(fused_conf), 
                            quality_score=obs.quality_score,
                            embedding=obs.embedding,
                            config_version=cfg_ver,
                        )
                elif obs.quality_category == "POOR":
                    label = f"[{track_id}] Poor Quality ({obs.quality_score:.0f})"
                else:
                    label = f"[{track_id}] Assessing {fused_id} ({track.valid_embeddings_count}/{self.track_manager.min_obs})"

                new_detections.append({
                    'bbox': tuple(full_bbox),
                    'label': label,
                    'score': fused_conf,
                    'last_rec_time': now,
                    'obs_count': track.valid_embeddings_count
                })

            self.last_detections = new_detections
            self._init_trackers(frame)

            self._processed_ts.append(now)
            while self._processed_ts and (now - self._processed_ts[0]) > 1.0:
                self._processed_ts.popleft()
            self.detector_fps = float(len(self._processed_ts))

        display = frame.copy()
        fh, fw = display.shape[:2]
        for det in self.last_detections:
            l, t, r, b = det['bbox']
            l, r, t, b = max(0, int(l)), min(fw-1, int(r)), max(0, int(t)), min(fh-1, int(b))
            cv2.rectangle(display, (l, t), (r, b), (0, 255, 0), 2)
            label_text = f"{det['label']} {det['score']:.2f}"
            (lw, lh), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            lx1 = max(l, 0)
            lx2 = min(l + lw + 8, fw - 1)
            cv2.rectangle(display, (lx1, b - lh - 8), (lx2, b), (0, 255, 0), cv2.FILLED)
            cv2.putText(display, label_text, (lx1 + 4, b - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        now_d = time.time()
        self._display_ts.append(now_d)
        while self._display_ts and (now_d - self._display_ts[0]) > 1.0:
            self._display_ts.popleft()
        self.display_fps = float(len(self._display_ts))
        
        self._display_fps_history.append(self.display_fps)
        if self.cpu_tier == 'auto' and not self.lock_resolution and len(self._display_fps_history) == 90 and (now_d - self.last_tier_shift_time) > 5.0:
            avg_fps = sum(self._display_fps_history) / 90.0
            tier_order = ['slow', 'mid', 'fast']
            curr_idx = tier_order.index(self.current_tier_name)
            cal_idx = tier_order.index(self.calibrated_tier_name)

            if avg_fps < 25.0 and curr_idx > 0:
                self.current_tier_name = tier_order[curr_idx - 1]
                t = TIERS[self.current_tier_name]
                self.frame_size = t['det_size']
                self.frame_skip = t['frame_skip']
                self.last_tier_shift_time = now_d
                self._display_fps_history.clear()
                logger.info("[%s] Adaptive shift DOWN to %s tier (Avg FPS: %.1f)", self.camera_id, self.current_tier_name, avg_fps)
            elif avg_fps > 29.0 and self.detector_fps > (30.0 / self.frame_skip) * 0.9 and curr_idx < cal_idx:
                self.current_tier_name = tier_order[curr_idx + 1]
                t = TIERS[self.current_tier_name]
                self.frame_size = t['det_size']
                self.frame_skip = t['frame_skip']
                self.last_tier_shift_time = now_d
                self._display_fps_history.clear()
                logger.info("[%s] Adaptive shift UP to %s tier (Avg FPS: %.1f)", self.camera_id, self.current_tier_name, avg_fps)
        
        fps_text = f"Arr: {self.fps:.1f} | Det: {self.detector_fps:.1f} | Disp: {self.display_fps:.1f}"
        if self._frame_count % 30 == 0:
            logger.info("[%s] %s", self.camera_id, fps_text)

        det_w, det_h = self.frame_size
        mode_lines = [
            f"Det: {det_w}x{det_h} | Cam: {self.capture_width}x{self.capture_height} | Frame: {fw}x{fh}",
            f"Model: {self.model_name} | Tier: {self.current_tier_name} | Skip: {self.frame_skip}",
        ]
        draw_text_block(display, mode_lines, corner='top_left')
        draw_text_block(display, [fps_text], corner='top_right', font_scale=0.7, thickness=2)

        with self.lock:
            self.latest_frame = display
        return display


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def build_sources(cfg: Dict[str, Any], webcam_index: Optional[int] = None) -> List[Tuple[str, Any]]:
    sources: List[Tuple[str, Any]] = []
    sources.append(('webcam', int(webcam_index if webcam_index is not None else cfg.get('webcam_index', 0))))
    for idx, url in enumerate(cfg.get('rtsp_urls', []) or []):
        sources.append((f'rtsp-{idx+1}', str(url)))
    dvr_ip = os.environ.get('DVR_IP', '').strip()
    dvr_username = os.environ.get('DVR_USERNAME', '').strip()
    dvr_password = os.environ.get('DVR_PASSWORD', '')
    if dvr_ip and dvr_username and dvr_password:
        dvr_port = os.environ.get('DVR_RTSP_PORT', '554').strip()
        dvr_path = os.environ.get('DVR_RTSP_PATH', 'Streaming/Channels/101').strip().lstrip('/')
        source = f'rtsp://{quote(dvr_username, safe="")}:{quote(dvr_password, safe="")}@{dvr_ip}:{dvr_port}/{dvr_path}'
        sources.append(('dvr-1', source))
    return sources


def main():
    options = parse_run_args('Facial recognition CPU runner', cpu=True)

    project_root = Path(__file__).resolve().parent
    cfg_path = project_root / 'config.yaml'
    cfg: Dict[str, Any] = load_config(cfg_path)

    default_det_w = int(cfg.get('cpu_inference_frame_width', cfg.get('inference_frame_width', 256)))
    default_det_h = int(cfg.get('cpu_inference_frame_height', cfg.get('inference_frame_height', 256)))
    det_w, det_h = resolve_det_size(options, default_det_w, default_det_h)
    frame_skip = options.frame_skip if options.frame_skip is not None else int(cfg.get('cpu_frame_skip', cfg.get('frame_skip', 5)))
    cpu_tier = options.tier or str(cfg.get('cpu_tier', 'auto')).lower()
    if options.max_quality and options.tier is None:
        cpu_tier = 'fast'
    lock_resolution = bool(
        options.max_quality or options.det_width is not None or options.det_height is not None
    )
    use_gpu = False
    fast_detector = bool(cfg.get('cpu_use_fast_detector', True))
    detector_model = resolve_model(options, str(cfg.get('cpu_detector_model', 'buffalo_s')))
    cam_w, cam_h = resolve_camera_size(
        options,
        int(cfg.get('camera_width', 640)),
        int(cfg.get('camera_height', 480)),
    )

    threshold = float(cfg.get('similarity_threshold', 0.60))
    gallery_path = str(project_root / cfg.get('gallery_path', 'known_faces/gallery.npz'))
    log_path = str(project_root / cfg.get('log_file', 'detections.csv'))
    database_url = os.environ.get('DATABASE_URL', cfg.get('database_url', None))

    logger.info(
        'Settings: detection=%dx%d model=%s camera=%dx%d tier=%s frame_skip=%d lock_resolution=%s',
        det_w, det_h, detector_model, cam_w, cam_h, cpu_tier, frame_skip, lock_resolution,
    )

    # detector and recognizer
    detector: Any = cast(Any, InsightFaceDetector(use_gpu=use_gpu, det_size=(det_w, det_h), model_name=detector_model, fast_detector=fast_detector))
    recognizer = Recognizer(gallery_path=gallery_path, threshold=threshold)

    # Create profile lookup function for database logging
    def profile_lookup(identity: str) -> Optional[str]:
        """Look up profile ID by identity name."""
        if identity == "Unknown":
            return None
        # Convert identity name to profile ID (simple mapping)
        return identity.lower().replace(" ", "-")
    
    det_logger = DetectionLogger(
        log_path=log_path,
        db_url=database_url,
        profile_lookup=profile_lookup
    )
    pending_saver = PendingSaver(project_root / 'pending')

    rec_interval = int(cfg.get('cpu_recognition_interval', 2))
    pipelines: List[CpuCameraPipeline] = []
    from quality import FaceQualityAssessor
    quality_assessor = FaceQualityAssessor(cfg.get('quality_thresholds', {}))

    for cam_id, src in build_sources(cfg, options.webcam_index):
        p = CpuCameraPipeline(
            cam_id,
            src,
            detector,
            recognizer,
            det_logger,
            frame_size=(det_w, det_h),
            frame_skip=frame_skip,
            recognition_interval=rec_interval,
            pending_saver=pending_saver,
            cpu_tier=cpu_tier,
            capture_width=cam_w,
            capture_height=cam_h,
            lock_resolution=lock_resolution,
            model_name=detector_model,
            quality_assessor=quality_assessor,
            track_fusion_cfg=cfg.get('track_fusion', {}),
        )
        pipelines.append(p)

    for p in pipelines:
        p.start()

    stop_event = threading.Event()

    def handle(sig: int, frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    for p in pipelines:
        cv2.namedWindow(p.camera_id, cv2.WINDOW_NORMAL)

    frame_publishers = [
        EdgeFramePublisher(pipeline.camera_id, lambda pipeline=pipeline: pipeline.latest_frame)
        for pipeline in pipelines
    ]
    for publisher in frame_publishers:
        publisher.start()

    try:
        while not stop_event.is_set():
            for p in pipelines:
                f = p.step()
                if f is not None:
                    cv2.imshow(p.camera_id, f)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            # small sleep to let OS schedule
            time.sleep(0.001)
    finally:
        for publisher in frame_publishers:
            publisher.stop()
        for p in pipelines:
            p.stop()
        det_logger.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
