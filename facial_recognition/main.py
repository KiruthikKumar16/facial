import signal
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from capture import CameraCapture
from detector import InsightFaceDetector
from logger import DetectionLogger
from recognizer import Recognizer


class CameraPipeline:
    def __init__(self, camera_id: str, source: str | int, detector: InsightFaceDetector, recognizer: Recognizer, logger: DetectionLogger, frame_size: tuple[int, int]) -> None:
        self.camera_id = camera_id
        self.source = source
        self.detector = detector
        self.recognizer = recognizer
        self.logger = logger
        self.frame_size = frame_size
        self.latest_frame = None
        self.latest_frame_lock = threading.Lock()
        self.last_frame_time = None
        self.fps = 0.0
        self.capture = CameraCapture(source, camera_id, self.process_frame, reconnect_interval=10)

    def start(self) -> None:
        self.capture.start()

    def stop(self) -> None:
        self.capture.stop()
        self.capture.join(timeout=5)

    def process_frame(self, camera_id: str, frame: any) -> None:
        now = time.time()
        if self.last_frame_time is not None:
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(now - self.last_frame_time, 1e-6))
        self.last_frame_time = now

        small_frame = cv2.resize(frame, self.frame_size, interpolation=cv2.INTER_LINEAR)
        detections = self.detector.detect(small_frame)
        annotated_frame = frame.copy()

        for face in detections:
            bbox = face['bbox']
            embedding = face['embedding']
            identity, confidence = self.recognizer.recognize(embedding)
            self.logger.log_detection(camera_id, bbox, identity, confidence)
            self._annotate_frame(annotated_frame, bbox, identity, confidence, small_frame.shape[:2])

        self._draw_fps(annotated_frame)
        with self.latest_frame_lock:
            self.latest_frame = annotated_frame

    def get_frame(self) -> any:
        with self.latest_frame_lock:
            return None if self.latest_frame is None else self.latest_frame.copy()

    def _annotate_frame(self, frame: any, bbox: list[int], identity: str, confidence: float, source_shape: tuple[int, int]) -> None:
        frame_height, frame_width = frame.shape[:2]
        source_h, source_w = source_shape
        x_scale = frame_width / source_w
        y_scale = frame_height / source_h

        left, top, right, bottom = bbox
        left = int(left * x_scale)
        right = int(right * x_scale)
        top = int(top * y_scale)
        bottom = int(bottom * y_scale)

        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        label = f'{identity} ({confidence:.2f})' if identity != 'Unknown' else 'Unknown'
        cv2.rectangle(frame, (left, bottom - 24), (right, bottom), (0, 255, 0), cv2.FILLED)
        cv2.putText(frame, label, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    def _draw_fps(self, frame: any) -> None:
        fps_text = f'FPS: {self.fps:.1f}'
        frame_height, frame_width = frame.shape[:2]
        text_size, _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        text_width, text_height = text_size
        x = frame_width - text_width - 12
        y = text_height + 12

        cv2.rectangle(frame, (x - 8, y - text_height - 4), (x + text_width + 8, y + 8), (0, 0, 0), cv2.FILLED)
        cv2.putText(frame, fps_text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)


def load_config(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def build_camera_sources(config: dict) -> list[tuple[str, str | int]]:
    sources = []
    sources.append(('webcam', int(config.get('webcam_index', 0))))
    for idx, url in enumerate(config.get('rtsp_urls', []) or []):
        sources.append((f'rtsp-{idx + 1}', str(url)))
    return sources


def main() -> None:
    config_path = Path(__file__).resolve().parent / 'config.yaml'
    config = load_config(config_path)
    threshold = float(config.get('similarity_threshold', 0.60))
    use_gpu = bool(config.get('use_gpu', False))
    frame_width = int(config.get('inference_frame_width', 640))
    frame_height = int(config.get('inference_frame_height', 640))
    reconnect_interval = int(config.get('reconnect_interval_seconds', 10))
    gallery_path = str(Path(config.get('gallery_path', 'known_faces/gallery.npz')).resolve())
    log_path = str(Path(config.get('log_file', 'detections.csv')).resolve())

    detector = InsightFaceDetector(use_gpu=use_gpu, det_size=(frame_width, frame_height))
    recognizer = Recognizer(gallery_path=gallery_path, threshold=threshold)
    logger = DetectionLogger(log_path=log_path)

    camera_pipelines = []
    for camera_id, source in build_camera_sources(config):
        pipeline = CameraPipeline(
            camera_id=camera_id,
            source=source,
            detector=detector,
            recognizer=recognizer,
            logger=logger,
            frame_size=(frame_width, frame_height),
        )
        pipeline.capture.reconnect_interval = reconnect_interval
        camera_pipelines.append(pipeline)

    for pipeline in camera_pipelines:
        pipeline.start()

    stop_event = threading.Event()

    def handle_signal(signum, frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while not stop_event.is_set():
            for pipeline in camera_pipelines:
                frame = pipeline.get_frame()
                if frame is not None:
                    cv2.imshow(pipeline.camera_id, frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        for pipeline in camera_pipelines:
            pipeline.stop()
        logger.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
