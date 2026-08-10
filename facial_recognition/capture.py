import threading
import time
from typing import Any, Callable

import cv2
import traceback


class CameraCapture(threading.Thread):
    def __init__(self, source: str | int, camera_id: str, frame_callback: Callable[[str, Any], None], reconnect_interval: int) -> None:
        super().__init__(daemon=True)
        self.source = source
        self.camera_id = camera_id
        self.frame_callback: Callable[[str, Any], None] = frame_callback
        self.reconnect_interval = reconnect_interval
        self._stop_event = threading.Event()
        self._capture: Any = None

    def run(self) -> None:
        while not self._stop_event.is_set():
            if self._capture is None or not self._capture.isOpened():
                self._connect()
                if self._capture is None or not self._capture.isOpened():
                    time.sleep(self.reconnect_interval)
                    continue

            ret, frame = self._capture.read()
            if not ret or frame is None:
                self._release_capture()
                time.sleep(self.reconnect_interval)
                continue

            try:
                self.frame_callback(self.camera_id, frame)
            except Exception as exc:
                # Log the exception so camera failures are visible instead of silently swallowed
                try:
                    print(f"[{self.camera_id}] frame processing error: {exc}")
                    traceback.print_exc()
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
