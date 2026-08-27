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
    """Uploads the latest annotated frame to Render over authenticated HTTPS."""

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

    def _upload_url(self) -> str:
        return f"{self.api_url}/api/internal/cameras/{quote(self.camera_id, safe='')}/frame"

    def _run(self) -> None:
        try:
            import requests
        except ImportError:
            logger.error("Cloud video relay needs requests. Install requirements.txt again.")
            return

        retry_seconds, interval = 1.0, 1.0 / self.fps
        session = requests.Session()
        connected = False
        while not self._stop.is_set():
            try:
                frame = self.get_frame()
                if frame is None:
                    self._stop.wait(interval)
                    continue

                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                if not ok:
                    self._stop.wait(interval)
                    continue

                response = session.post(
                    self._upload_url(),
                    data=encoded.tobytes(),
                    headers={
                        "Content-Type": "image/jpeg",
                        "X-API-Key": self.api_key,
                    },
                    timeout=10,
                )
                response.raise_for_status()
                if not connected:
                    logger.info("Cloud video relay is uploading frames for camera '%s'", self.camera_id)
                    connected = True
                retry_seconds = 1.0
                self._stop.wait(interval)
            except Exception as exc:
                connected = False
                logger.warning("Cloud video relay upload failed for '%s': %s", self.camera_id, exc)
                self._stop.wait(retry_seconds)
                retry_seconds = min(retry_seconds * 2, 30.0)
