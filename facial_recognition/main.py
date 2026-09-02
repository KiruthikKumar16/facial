import os
import signal
import threading
import time
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, cast

import cv2
import numpy as np
import yaml
import logging

try:
    from dotenv import load_dotenv, find_dotenv

    def _resolve_env_path() -> Path | None:
        """Resolve the single root .env file.

        Preference:
        1. <repo-root>/.env   (one level up from facial_recognition/ package)
        2. find_dotenv fallback (walks from cwd upward)
        """
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

cv2: Any = cv2
yaml: Any = yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)

try:
    from .capture import CameraCapture
    from .detector import InsightFaceDetector
    from .logger import DetectionLogger
    from .recognizer import Recognizer
    from .pending import PendingSaver
    from .cli import (
        MAX_CAMERA_HEIGHT,
        MAX_CAMERA_WIDTH,
        MAX_DET_SIZE,
        MAX_MODEL,
        parse_run_args,
        resolve_camera_size,
        resolve_det_size,
        resolve_model,
    )
    from .overlay import draw_text_block
    from .edge_stream import EdgeFramePublisher
except ImportError:
    from capture import CameraCapture
    from detector import InsightFaceDetector  # type: ignore[reportMissingImports]
    from logger import DetectionLogger
    from recognizer import Recognizer
    from pending import PendingSaver
    from cli import (
        MAX_CAMERA_HEIGHT,
        MAX_CAMERA_WIDTH,
        MAX_DET_SIZE,
        MAX_MODEL,
        parse_run_args,
        resolve_camera_size,
        resolve_det_size,
        resolve_model,
    )
    from overlay import draw_text_block
    from edge_stream import EdgeFramePublisher


class CameraPipeline:
    def __init__(
        self,
        camera_id: str,
        source: str | int,
        detector: Any,
        recognizer: Recognizer,
        logger: DetectionLogger,
        frame_size: tuple[int, int],
        pending_saver: PendingSaver | None = None,
        capture_width: int = MAX_CAMERA_WIDTH,
        capture_height: int = MAX_CAMERA_HEIGHT,
        reconnect_interval: int = 10,
        model_name: str = MAX_MODEL,
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
        self.quality_assessor = quality_assessor
        self.camera_config_manager = camera_config_manager
        self.frame_size = frame_size
        self.capture_width = capture_width
        self.capture_height = capture_height
        self.model_name = model_name
        self.latest_frame = None
        self.latest_frame_lock = threading.Lock()
        self.last_frame_time = None
        self.fps = 0.0
        
        # Temporal Track Fusion Manager
        from facial_recognition.track_fusion import TemporalTrackManager, FaceObservation
        track_cfg = track_fusion_cfg or {}
        
        # Apply camera-specific profile if available
        profile = None
        if self.camera_config_manager:
            profile = self.camera_config_manager.get_profile(self.camera_id)
            if profile:
                self.recognizer.threshold = profile.recognition_threshold
                
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

        self.capture = CameraCapture(
            source,
            camera_id,
            self.process_frame,
            reconnect_interval=reconnect_interval,
            capture_width=capture_width,
            capture_height=capture_height,
        )

    def start(self) -> None:
        logger.info('Starting CameraPipeline %s (source=%s)', self.camera_id, self.source)
        self.capture.start()

    def stop(self) -> None:
        logger.info('Stopping CameraPipeline %s', self.camera_id)
        self.capture.stop()
        self.capture.join(timeout=5)

    def process_frame(self, camera_id: str, frame: Any) -> None:
        from facial_recognition.track_fusion import FaceObservation
        now = time.time()
        dt = max(0.001, now - (self.last_frame_time or now))
        if self.last_frame_time is not None:
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(now - self.last_frame_time, 1e-6))
        self.last_frame_time = now

        small_frame: Any = cv2.resize(frame, self.frame_size, interpolation=cv2.INTER_LINEAR)
        detections: List[Dict[str, Any]] = cast(List[Dict[str, Any]], self.detector.detect(small_frame))
        annotated_frame: Any = frame.copy()

        fh, fw = frame.shape[:2]
        sh, sw = small_frame.shape[:2]
        x_scale = fw / sw
        y_scale = fh / sh

        frame_observations: List[FaceObservation] = []
        scaled_faces: List[Tuple[List[int], Any]] = []

        for face in detections:
            l, t, r, b = face['bbox']
            l, r = int(l * x_scale), int(r * x_scale)
            t, b = int(t * y_scale), int(b * y_scale)
            full_bbox = [l, t, r, b]

            # Scale landmarks if present
            scaled_kps = None
            if 'kps' in face and face['kps'] is not None:
                kps = np.array(face['kps'], dtype=np.float32)
                kps[:, 0] *= x_scale
                kps[:, 1] *= y_scale
                scaled_kps = kps

            quality_category = "HIGH"
            quality_score = 100.0
            
            if self.quality_assessor:
                cat, q_metrics = self.quality_assessor.assess(
                    frame, 
                    {**face, 'bbox': full_bbox, 'kps': scaled_kps}, 
                    dt=dt
                )
                quality_category = cat
                quality_score = q_metrics.get('score', 100.0)

            # Avoid generating unnecessary embeddings for unusable/poor quality faces
            emb = None
            if quality_category != "POOR":
                emb = self.detector.extract_embedding(frame, {**face, 'bbox': full_bbox, 'kps': scaled_kps})

            obs = FaceObservation(
                timestamp=now,
                bbox=full_bbox,
                quality_score=quality_score,
                quality_category=quality_category,
                confidence=float(face.get('det_score', 1.0)),
                embedding=emb,
            )
            frame_observations.append(obs)
            scaled_faces.append((full_bbox, emb))

        # Temporal Track Association & Identity Fusion
        track_pairs = self.track_manager.process_frame_observations(
            frame_observations,
            self.recognizer.labels,
            self.recognizer.embeddings,
            current_time=now,
        )

        for track, obs in track_pairs:
            full_bbox = obs.bbox
            track_id = track.track_id
            fused_id = track.fused_identity
            fused_conf = track.fused_confidence
            is_finalized = track.is_finalized

            if is_finalized:
                display_label = f"[{track_id}] {fused_id} ({fused_conf:.2f})*"
                self._annotate_frame(annotated_frame, full_bbox, display_label, fused_conf)
                cfg_ver = 1
                if self.camera_config_manager:
                    prof = self.camera_config_manager.get_profile(camera_id)
                    if prof:
                        cfg_ver = prof.version

                # Construct Version Bundle & Provenance Record
                try:
                    from facial_recognition.version_bundle import ModelConfigVersionBundle
                    from facial_recognition.provenance import ProvenanceTracker
                    
                    bundle = ModelConfigVersionBundle(
                        detection_model_version="scrfd_500m_bnkps_v1",
                        embedding_model_version="w600k_mbf_v1",
                        gallery_version=1,
                        threshold_version=1,
                        camera_config_version=cfg_ver,
                        algorithm_version="temporal_fusion_v2",
                    )
                    
                    prov_tracker = ProvenanceTracker(
                        camera_id=camera_id,
                        frame_reference=f"frm_{camera_id}_{int(now*1000)}",
                        track_id=track_id,
                    )
                    for o_idx in range(len(track.observations)):
                        prov_tracker.add_observation(f"obs_{track_id}_{o_idx+1}")
                    
                    if track.fused_embedding is not None:
                        prov_tracker.set_embedding_vector(track.fused_embedding)
                    prov_tracker.add_candidate(fused_id, fused_conf, rank=1)
                    
                    prov = prov_tracker.finalize(
                        event_id=f"evt_{camera_id}_{int(now*1000)}",
                        identity=fused_id,
                        confidence=fused_conf,
                        decision_tier="TEMPORAL_FUSED",
                    )
                except Exception:
                    bundle = None
                    prov = None

                self.logger.log_detection(
                    camera_id, 
                    full_bbox, 
                    fused_id, 
                    fused_conf, 
                    quality_score=obs.quality_score,
                    config_version=cfg_ver,
                    version_bundle=bundle,
                    provenance=prov,
                )
            elif obs.quality_category == "POOR":
                display_label = f"[{track_id}] Poor Quality ({obs.quality_score:.0f})"
                self._annotate_frame(annotated_frame, full_bbox, display_label, 0.0)
            else:
                display_label = f"[{track_id}] Assessing {fused_id} ({track.valid_embeddings_count}/{self.track_manager.min_obs})"
                self._annotate_frame(annotated_frame, full_bbox, display_label, fused_conf)

        self._draw_fps(annotated_frame, annotated_frame.shape[:2])
        with self.latest_frame_lock:
            self.latest_frame = annotated_frame
        self._draw_fps(annotated_frame, annotated_frame.shape[:2])
        with self.latest_frame_lock:
            self.latest_frame = annotated_frame

    def get_frame(self) -> Any:
        with self.latest_frame_lock:
            return None if self.latest_frame is None else self.latest_frame.copy()

    def _annotate_frame(self, frame: Any, bbox: list[int], identity: str, confidence: float) -> None:
        left, top, right, bottom = bbox
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        label = f'{identity} ({confidence:.2f})' if identity != 'Unknown' else 'Unknown'
        cv2.rectangle(frame, (left, bottom - 24), (right, bottom), (0, 255, 0), cv2.FILLED)
        cv2.putText(frame, label, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    def _draw_fps(self, frame: Any, frame_shape: tuple[int, int]) -> None:
        fh, fw = frame_shape
        det_w, det_h = self.frame_size
        mode_lines = [
            f'Det: {det_w}x{det_h} | Cam: {self.capture_width}x{self.capture_height} | Frame: {fw}x{fh}',
            f'Model: {self.model_name}',
        ]
        draw_text_block(frame, mode_lines, corner='top_left')
        draw_text_block(frame, [f'FPS: {self.fps:.1f}'], corner='top_right', font_scale=0.8, thickness=2)


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as stream:
        return yaml.safe_load(stream) or {}


def build_camera_sources(config: Dict[str, Any], webcam_index: Optional[int] = None) -> List[Tuple[str, Any]]:
    sources: List[Tuple[str, Any]] = []
    sources.append(('webcam', int(webcam_index if webcam_index is not None else config.get('webcam_index', 0))))
    rtsp_urls = cast(List[Any], config.get('rtsp_urls', []) or [])
    for idx, url in enumerate(rtsp_urls):
        sources.append((f'rtsp-{idx + 1}', str(url)))
    dvr_ip = os.environ.get('DVR_IP', '').strip()
    dvr_username = os.environ.get('DVR_USERNAME', '').strip()
    dvr_password = os.environ.get('DVR_PASSWORD', '')
    if dvr_ip and dvr_username and dvr_password:
        dvr_port = os.environ.get('DVR_RTSP_PORT', '554').strip()
        dvr_path = os.environ.get('DVR_RTSP_PATH', 'Streaming/Channels/101').strip().lstrip('/')
        source = f'rtsp://{quote(dvr_username, safe="")}:{quote(dvr_password, safe="")}@{dvr_ip}:{dvr_port}/{dvr_path}'
        sources.append(('dvr-1', source))
    return sources


def main() -> None:
    options = parse_run_args('Facial recognition (max-quality defaults)', cpu=False)

    project_root = Path(__file__).resolve().parent
    config_path = project_root / 'config.yaml'
    config: Dict[str, Any] = load_config(config_path)

    threshold = float(config.get('similarity_threshold', 0.35))
    use_gpu = bool(config.get('use_gpu', False))
    reconnect_interval = int(config.get('reconnect_interval_seconds', 10))

    default_det_w = int(config.get('inference_frame_width', MAX_DET_SIZE))
    default_det_h = int(config.get('inference_frame_height', MAX_DET_SIZE))
    if not options.det_width and not options.det_height and not options.max_quality:
        default_det_w, default_det_h = MAX_DET_SIZE, MAX_DET_SIZE
    det_w, det_h = resolve_det_size(options, default_det_w, default_det_h)
    model_name = resolve_model(options, MAX_MODEL)
    cam_w, cam_h = resolve_camera_size(options, MAX_CAMERA_WIDTH, MAX_CAMERA_HEIGHT)

    gallery_path = str(project_root / config.get('gallery_path', 'known_faces/gallery.npz'))
    log_path = str(project_root / config.get('log_file', 'detections.csv'))
    database_url = os.environ.get('DATABASE_URL', config.get('database_url', None))

    logger.info(
        'Settings: detection=%dx%d model=%s camera=%dx%d gpu=%s',
        det_w, det_h, model_name, cam_w, cam_h, use_gpu,
    )

    detector: Any = cast(
        Any,
        InsightFaceDetector(use_gpu=use_gpu, det_size=(det_w, det_h), model_name=model_name),
    )
    recognizer = Recognizer(gallery_path=gallery_path, threshold=threshold)

    def profile_lookup(identity: str) -> Optional[str]:
        if identity == 'Unknown':
            return None
        return identity.lower().replace(' ', '-')

    det_logger = DetectionLogger(
        log_path=log_path,
        db_url=database_url,
        profile_lookup=profile_lookup,
    )

    from facial_recognition.quality import FaceQualityAssessor
    quality_assessor = FaceQualityAssessor(config.get('quality_thresholds', {}))

    camera_pipelines: List[Any] = []
    pending_saver = PendingSaver(project_root / 'pending')
    for camera_id, source in build_camera_sources(config, options.webcam_index):
        pipeline: Any = CameraPipeline(
            camera_id=camera_id,
            source=source,
            detector=detector,
            recognizer=recognizer,
            logger=det_logger,
            frame_size=(det_w, det_h),
            pending_saver=pending_saver,
            capture_width=cam_w,
            capture_height=cam_h,
            reconnect_interval=reconnect_interval,
            model_name=model_name,
            quality_assessor=quality_assessor,
            track_fusion_cfg=config.get('track_fusion', {}),
        )
        camera_pipelines.append(pipeline)

    for pipeline in camera_pipelines:
        pipeline.start()

    frame_publishers = [
        EdgeFramePublisher(pipeline.camera_id, pipeline.get_frame)
        for pipeline in camera_pipelines
    ]
    for publisher in frame_publishers:
        publisher.start()

    stop_event = threading.Event()

    def handle_signal(signum: int, frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    for pipeline in camera_pipelines:
        cv2.namedWindow(pipeline.camera_id, cv2.WINDOW_NORMAL)

    try:
        logger.info('Starting main loop, pipelines=%d', len(camera_pipelines))
        while not stop_event.is_set():
            for pipeline in camera_pipelines:
                frame = pipeline.get_frame()
                if frame is not None:
                    cv2.imshow(pipeline.camera_id, frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        for publisher in frame_publishers:
            publisher.stop()
        for pipeline in camera_pipelines:
            pipeline.stop()
        det_logger.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
