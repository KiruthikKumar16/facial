"""Publish annotated camera frames from the local edge node to the cloud API."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable
from urllib.parse import quote

import cv2

logger = logging.getLogger(__name__)


class EdgeFramePublisher:
    """Keeps one outbound WebSocket per camera and sends only the latest frame."""

    def __init__(self, camera_id: str, get_frame: Callable[[], Any], *, api_url: str | None = None,
                 api_key: str | None = None, fps: float | None = None, jpeg_quality: int | None = None) -> None:
        self.camera_id = camera_id
        self.get_frame = get_frame
        self.api_url = (api_url or os.environ.get("API_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("EDGE_API_KEY", "")
        self.fps = max(1.0, float(fps or os.environ.get("EDGE_STREAM_FPS", "8")))
        self.jpeg_quality = max(30, min(95, int(jpeg_quality or os.environ.get("EDGE_STREAM_JPEG_QUALITY", "75"))))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_url and self.api_key and self.api_url.startswith(("http://", "https://")))

    def start(self) -> None:
        if not self.enabled:
            logger.info("Cloud video relay disabled; set API_URL and EDGE_API_KEY to enable it.")
            return
        self._thread = threading.Thread(target=self._run, name=f"edge-frame-publisher-{self.camera_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _websocket_url(self) -> str:
        base = self.api_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        return f"{base}/ws/video/push/{quote(self.camera_id, safe='')}?api_key={quote(self.api_key, safe='')}"

    def _run(self) -> None:
        try:
            import websocket
        except ImportError:
            logger.error("Cloud video relay needs websocket-client. Install requirements.txt again.")
            return

        retry_seconds, interval = 1.0, 1.0 / self.fps
        while not self._stop.is_set():
            ws = None
            try:
                ws = websocket.create_connection(self._websocket_url(), timeout=10)
                ws.settimeout(10)
                retry_seconds = 1.0
                logger.info("Cloud video relay connected for camera '%s'", self.camera_id)
                while not self._stop.is_set():
                    started = time.monotonic()
                    frame = self.get_frame()
                    if frame is not None:
                        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                        if ok:
                            ws.send(encoded.tobytes(), opcode=websocket.ABNF.OPCODE_BINARY)
                    self._stop.wait(max(0.0, interval - (time.monotonic() - started)))
            except Exception as exc:
                logger.warning("Cloud video relay disconnected for '%s': %s", self.camera_id, exc)
                self._stop.wait(retry_seconds)
                retry_seconds = min(retry_seconds * 2, 30.0)
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
