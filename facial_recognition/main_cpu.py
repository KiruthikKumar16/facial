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
from typing import Any, Deque, Dict, List, Optional, Tuple, cast
import logging

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
from collections import deque


class CpuCameraPipeline:
    def __init__(
        self,
        camera_id: str,
        source: Any,
        detector: Any,
        recognizer: Any,
        logger: Any,
        frame_size: Tuple[int, int] = (320, 320),
        frame_skip: int = 2,
        recognition_interval: int = 4,
        use_tracker: bool = True,
        pending_saver: Optional[PendingSaver] = None,
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.detector = detector
        self.recognizer = recognizer
        self.logger = logger
        self.pending_saver = pending_saver
        self.frame_size = frame_size
        self.frame_skip = max(1, int(frame_skip))
        self.recognition_interval = max(1, int(recognition_interval))
        self.use_tracker = bool(use_tracker)
        self._frame_count = 0
        self._processed_count = 0
        self.latest_frame: Optional[Any] = None
        self.lock = threading.Lock()
        # store last processed detections (in full-frame coords) to re-draw on skipped frames
        self.last_detections: List[Dict[str, Any]] = []
        self.face_trackers: List[Any] = []
        self._tracker_warning_printed = False
        # timestamps of detector calls for computing detector FPS
        self._processed_ts: Deque[float] = deque()
        self.detector_fps = 0.0
        # timestamps of frame updates for computing display FPS
        self._display_ts: Deque[float] = deque()
        self.display_fps = 0.0
        # CameraCapture runs in a thread and calls process_frame
        self.capture = CameraCapture(source, camera_id, self.process_frame, reconnect_interval=10)
        self.last_fps_time = None
        self.fps = 0.0

    def start(self):
        logger.info('Starting CameraPipeline %s (source=%s)', self.camera_id, self.source)
        self.capture.start()

    def stop(self):
        logger.info('Stopping CameraPipeline %s', self.camera_id)
        self.capture.stop()
        self.capture.join(timeout=5)

    def _create_tracker(self) -> Optional[Any]:
        try:
            if hasattr(cv2, 'legacy') and hasattr(cv2.legacy, 'TrackerMOSSE_create'):
                return cv2.legacy.TrackerMOSSE_create()
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
                    print(
                        "Warning: OpenCV tracker unavailable. Install opencv-contrib-python "
                        "to enable tracker-based CPU frame skipping."
                    )
                    self._tracker_warning_printed = True
                self.use_tracker = False
                self.face_trackers = []
                return

            l, t, r, b = det['bbox']
            w = max(1, r - l)
            h = max(1, b - t)
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

    def process_frame(self, camera_id: str, frame: Any) -> None:
        logger.debug('[%s] process_frame start (frame_count=%d)', self.camera_id, self._frame_count)
        # update FPS using arrival times
        now = time.time()
        if self.last_fps_time is not None:
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(now - self.last_fps_time, 1e-6))
        self.last_fps_time = now

        self._frame_count += 1
        if (self._frame_count % self.frame_skip) != 0:
            if self.last_detections:
                self._update_tracked_boxes(frame)

            # Draw last known detections onto this frame for display (no heavy processing)
            display = frame.copy()
            fh, fw = display.shape[:2]
            for det in self.last_detections:
                l, t, r, b = det['bbox']
                # clamp
                l = max(0, min(fw - 1, int(l)))
                r = max(0, min(fw - 1, int(r)))
                t = max(0, min(fh - 1, int(t)))
                b = max(0, min(fh - 1, int(b)))
                cv2.rectangle(display, (l, t), (r, b), (0, 255, 0), 2)
                label_text = f"{det['label']} {det['score']:.2f}"
                (lw, lh), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                lx1 = max(l, 0)
                lx2 = min(l + lw + 8, fw - 1)
                cv2.rectangle(display, (lx1, b - lh - 8), (lx2, b), (0, 255, 0), cv2.FILLED)
                cv2.putText(display, label_text, (lx1 + 4, b - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            # draw arrival FPS and processing FPS
            now_d = time.time()
            self._display_ts.append(now_d)
            while self._display_ts and (now_d - self._display_ts[0]) > 1.0:
                self._display_ts.popleft()
            self.display_fps = float(len(self._display_ts))
            fps_text = f"Arr: {self.fps:.1f} | Det: {self.detector_fps:.1f} | Disp: {self.display_fps:.1f}"
            (tw, th), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            x = fw - tw - 10
            y = 20
            cv2.rectangle(display, (x - 6, y - th - 4), (x + tw + 6, y + 6), (0, 0, 0), cv2.FILLED)
            cv2.putText(display, fps_text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            with self.lock:
                self.latest_frame = display
            return

        self._processed_count += 1
        # optionally skip detection/recognition when last detection is still valid
        if self.last_detections and (self._processed_count % self.recognition_interval) != 0:
            if self._update_tracked_boxes(frame):
                # If trackers are still valid, simply redraw current tracked boxes.
                annotated = frame.copy()
                fh, fw = annotated.shape[:2]
                for det in self.last_detections:
                    l, t, r, b = det['bbox']
                    l = max(0, min(fw - 1, int(l)))
                    r = max(0, min(fw - 1, int(r)))
                    t = max(0, min(fh - 1, int(t)))
                    b = max(0, min(fh - 1, int(b)))
                    cv2.rectangle(annotated, (l, t), (r, b), (0, 255, 0), 2)
                    label_text = f"{det['label']} {det['score']:.2f}"
                    (lw, lh), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    lx1 = max(l, 0)
                    lx2 = min(l + lw + 8, fw - 1)
                    cv2.rectangle(annotated, (lx1, b - lh - 8), (lx2, b), (0, 255, 0), cv2.FILLED)
                    cv2.putText(annotated, label_text, (lx1 + 4, b - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

                now_d = time.time()
                self._display_ts.append(now_d)
                while self._display_ts and (now_d - self._display_ts[0]) > 1.0:
                    self._display_ts.popleft()
                self.display_fps = float(len(self._display_ts))
                fps_text = f"Arr: {self.fps:.1f} | Det: {self.detector_fps:.1f} | Disp: {self.display_fps:.1f}"
                (tw, th), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                x = fw - tw - 10
                y = 20
                cv2.rectangle(annotated, (x - 6, y - th - 4), (x + tw + 6, y + 6), (0, 0, 0), cv2.FILLED)
                cv2.putText(annotated, fps_text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                with self.lock:
                    self.latest_frame = annotated
                return
            # if tracker fails, fall through to a fresh detection run

        # Resize once for inference
        small: Any = cv2.resize(frame, self.frame_size, interpolation=cv2.INTER_LINEAR)
        det_start = time.perf_counter()
        detections: List[Dict[str, Any]] = cast(List[Dict[str, Any]], self.detector.detect(small))
        det_dur = (time.perf_counter() - det_start) * 1000.0
        logger.debug('[%s] detection pass took %.2f ms, results=%d', self.camera_id, det_dur, len(detections))

        annotated: Any = frame.copy()
        # annotate detections (scale boxes)
        fh, fw = annotated.shape[:2]
        sh, sw = small.shape[:2]
        x_scale = fw / sw
        y_scale = fh / sh

        self.last_detections = []
        for face in detections:
            bbox = cast(Tuple[int, int, int, int], face['bbox'])
            l, t, r, b = bbox
            l = int(l * x_scale)
            r = int(r * x_scale)
            t = int(t * y_scale)
            b = int(b * y_scale)
            emb: Any = face['embedding']
            identity, score = self.recognizer.recognize(emb)
            display_label = identity
            if identity == 'Unknown' and self.pending_saver is not None:
                try:
                    cropped = frame[t:b, l:r].copy()
                    emb_arr = np.asarray(emb, dtype=np.float32)
                    pending_label = self.pending_saver.save(emb_arr, cropped)
                    if pending_label is not None:
                        display_label = pending_label
                except Exception:
                    pass
            # minimal overlay
            cv2.rectangle(annotated, (l, t), (r, b), (0, 255, 0), 2)
            label = display_label
            label_text = f"{label} {score:.2f}"
            (lw, lh), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            lx1 = max(l, 0)
            lx2 = min(l + lw + 8, fw - 1)
            cv2.rectangle(annotated, (lx1, b - lh - 8), (lx2, b), (0, 255, 0), cv2.FILLED)
            cv2.putText(annotated, label_text, (lx1 + 4, b - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            # keep light logging
            if self.logger is not None:
                self.logger.log_detection(camera_id, [l, t, r, b], label, float(score))
            # store scaled bbox+label for redraw on skipped frames
            self.last_detections.append({'bbox': (l, t, r, b), 'label': label, 'score': float(score)})

        # initialize trackers for repeated frames after a detection pass
        self._init_trackers(frame)

        # record detector timestamp and compute detector FPS over 1s window
        now_p = time.time()
        self._processed_ts.append(now_p)
        while self._processed_ts and (now_p - self._processed_ts[0]) > 1.0:
            self._processed_ts.popleft()
        self.detector_fps = float(len(self._processed_ts))

        # record display frame update timestamp and compute display FPS
        self._display_ts.append(now_p)
        while self._display_ts and (now_p - self._display_ts[0]) > 1.0:
            self._display_ts.popleft()
        self.display_fps = float(len(self._display_ts))

        # draw arrival + detector + display fps small in top-right
        fps_text = f"Arr: {self.fps:.1f} | Det: {self.detector_fps:.1f} | Disp: {self.display_fps:.1f}"
        (tw, th), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        x = fw - tw - 10
        y = 20
        cv2.rectangle(annotated, (x - 6, y - th - 4), (x + tw + 6, y + 6), (0, 0, 0), cv2.FILLED)
        cv2.putText(annotated, fps_text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        with self.lock:
            self.latest_frame = annotated

    def get_frame(self) -> Optional[Any]:
        with self.lock:
            return None if self.latest_frame is None else self.latest_frame.copy()


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def build_sources(cfg: Dict[str, Any]) -> List[Tuple[str, Any]]:
    sources: List[Tuple[str, Any]] = []
    sources.append(('webcam', int(cfg.get('webcam_index', 0))))
    for idx, url in enumerate(cfg.get('rtsp_urls', []) or []):
        sources.append((f'rtsp-{idx+1}', str(url)))
    return sources


def main():
    project_root = Path(__file__).resolve().parent.parent
    cfg_path = project_root / 'config.yaml'
    cfg: Dict[str, Any] = load_config(cfg_path)

    # tuned defaults for CPU
    det_w = int(cfg.get('cpu_inference_frame_width', cfg.get('inference_frame_width', 320)))
    det_h = int(cfg.get('cpu_inference_frame_height', cfg.get('inference_frame_height', 320)))
    frame_skip = int(cfg.get('cpu_frame_skip', cfg.get('frame_skip', 4)))
    use_gpu = False
    fast_detector = bool(cfg.get('cpu_use_fast_detector', True))
    detector_model = str(cfg.get('cpu_detector_model', 'buffalo_s'))

    threshold = float(cfg.get('similarity_threshold', 0.60))
    gallery_path = str(project_root / cfg.get('gallery_path', 'known_faces/gallery.npz'))
    log_path = str(project_root / cfg.get('log_file', 'detections.csv'))
    database_url = cfg.get('database_url', None)

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
    
    logger = DetectionLogger(
        log_path=log_path,
        db_url=database_url,
        profile_lookup=profile_lookup
    )
    pending_saver = PendingSaver()

    rec_interval = int(cfg.get('cpu_recognition_interval', 2))
    pipelines: List[CpuCameraPipeline] = []
    for cam_id, src in build_sources(cfg):
        p = CpuCameraPipeline(
            cam_id,
            src,
            detector,
            recognizer,
            logger,
            frame_size=(det_w, det_h),
            frame_skip=frame_skip,
            recognition_interval=rec_interval,
            pending_saver=pending_saver,
        )
        pipelines.append(p)

    for p in pipelines:
        p.start()

    stop_event = threading.Event()

    def handle(sig: int, frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    try:
        while not stop_event.is_set():
            for p in pipelines:
                f = p.get_frame()
                if f is not None:
                    cv2.imshow(p.camera_id, f)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            # small sleep to let OS schedule
            time.sleep(0.001)
    finally:
        for p in pipelines:
            p.stop()
        logger.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
