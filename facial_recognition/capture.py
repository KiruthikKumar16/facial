import threading
import time
from typing import Any, Callable

import logging
import cv2

logger = logging.getLogger(__name__)


class CameraCapture(threading.Thread):
    def __init__(self, source: str | int, camera_id: str, frame_callback: Callable[[str, Any], None], reconnect_interval: int) -> None:
        super().__init__(daemon=True)
        self.source = 0
        self.camera_id = camera_id
        self.frame_callback: Callable[[str, Any], None] = frame_callback
        self.reconnect_interval = reconnect_interval
        self._stop_event = threading.Event()
        self._capture: Any = None

    def run(self) -> None:
        while not self._stop_event.is_set():
            if self._capture is None or not self._capture.isOpened():
                logger.info('[%s] connecting to source %s', self.camera_id, self.source)
                self._connect()
                if self._capture is None or not self._capture.isOpened():
                    logger.warning('[%s] capture not opened, retry in %s seconds', self.camera_id, self.reconnect_interval)
                    time.sleep(self.reconnect_interval)
                    continue

            ret, frame = self._capture.read()
            if not ret or frame is None:
                logger.warning('[%s] frame read failed, reconnecting', self.camera_id)
                self._release_capture()
                time.sleep(self.reconnect_interval)
                continue

            try:
                start = time.perf_counter()
                self.frame_callback(self.camera_id, frame)
                dur = (time.perf_counter() - start) * 1000.0
                logger.debug('[%s] frame callback took %.2f ms', self.camera_id, dur)
            except Exception as exc:
                # Log the exception so camera failures are visible instead of silently swallowed
                try:
                    logger.exception('[%s] frame processing error: %s', self.camera_id, exc)
                except Exception:
                    # Best-effort logging; never allow logging to raise
                    pass

        self._release_capture()

    def _connect(self) -> None:
        self._release_capture()
        self._capture = cv2.VideoCapture(self.source)

    def _release_capture(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None

    def stop(self) -> None:
        self._stop_event.set()
