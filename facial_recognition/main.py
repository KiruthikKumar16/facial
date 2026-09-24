"""
Entry point for running facial recognition surveillance system with GPU support.
"""

import sys
from pathlib import Path

# Add facial_recognition module to path
sys.path.insert(0, str(Path(__file__).parent))

from facial_recognition.main_cpu import CpuCameraPipeline, build_sources, load_config
from facial_recognition.cli import parse_run_args, resolve_det_size, resolve_model, resolve_camera_size
from facial_recognition.detector import InsightFaceDetector
from facial_recognition.recognizer import Recognizer
from facial_recognition.logger import DetectionLogger
from facial_recognition.pending import PendingSaver
from facial_recognition.edge_stream import EdgeFramePublisher
from facial_recognition.quality import FaceQualityAssessor
import threading
import signal
import time
import os
import yaml
import cv2
from typing import Any, Dict, List, Optional, cast

# bind thread limits early to help native libs
os.environ.setdefault('OMP_NUM_THREADS', os.environ.get('OMP_NUM_THREADS', '4'))
os.environ.setdefault('MKL_NUM_THREADS', os.environ.get('MKL_NUM_THREADS', '4'))
os.environ.setdefault('OPENBLAS_NUM_THREADS', os.environ.get('OPENBLAS_NUM_THREADS', '4'))

import cv2  # type: ignore[reportMissingTypeStubs]
import yaml  # type: ignore[reportMissingTypeStubs]

cv2: Any = cv2
yaml: Any = yaml

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    options = parse_run_args('Facial recognition surveillance system', cpu=False)

    project_root = Path(__file__).resolve().parent
    cfg_path = project_root / 'config.yaml'
    cfg: Dict[str, Any] = load_config(cfg_path)

    default_det_w = int(cfg.get('inference_frame_width', 640))
    default_det_h = int(cfg.get('inference_frame_height', 640))
    det_w, det_h = resolve_det_size(options, default_det_w, default_det_h)
    frame_skip = options.frame_skip if options.frame_skip is not None else int(cfg.get('frame_skip', 5))
    # For GPU, we don't use cpu_tier, but we can set it to 'fixed' to disable adaptive tiering in CpuCameraPipeline
    cpu_tier = 'fixed'  # Disable adaptive tiering for GPU
    lock_resolution = bool(
        options.max_quality or options.det_width is not None or options.det_height is not None
    )
    use_gpu = bool(cfg.get('use_gpu', False))
    fast_detector = bool(cfg.get('cpu_use_fast_detector', False))  # Usually false for GPU
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
        'Settings: detection=%dx%d model=%s camera=%dx%d tier=%s frame_skip=%d lock_resolution=%s use_gpu=%s',
        det_w, det_h, detector_model, cam_w, cam_h, cpu_tier, frame_skip, lock_resolution, use_gpu,
    )

    # detector and recognizer
    remote_cfg = cfg.get('remote_detection', {})
    remote_enabled = remote_cfg.get('enabled', False)

    if remote_enabled:
        from remote_detector import RemoteInsightFaceDetector
        detector: Any = RemoteInsightFaceDetector(
            endpoint=remote_cfg.get('endpoint', 'http://localhost:8000/detect'),
            det_size=tuple(remote_cfg.get('det_size', [det_w, det_h])),
            model_name=detector_model,
            timeout=remote_cfg.get('timeout', 5.0),
            fallback_to_local=remote_cfg.get('fallback_to_local', True)
        )
        logger.info(f"Using remote detector at {remote_cfg.get('endpoint')}")
    else:
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

    rec_interval = int(cfg.get('recognition_interval', 2))
    pipelines: List[CpuCameraPipeline] = []
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