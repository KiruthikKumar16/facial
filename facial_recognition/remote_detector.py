"""
Remote InsightFace Detector client.
Offloads face detection and recognition to a remote service (Google Colab, Kaggle, or edge GPU server)
with automatic fallback to local detection if the remote service is unavailable.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
import requests

from facial_recognition.detector import InsightFaceDetector

logger = logging.getLogger(__name__)


class RemoteInsightFaceDetector:
    """Client for remote face detection microservice with local fallback."""

    def __init__(
        self,
        endpoint: str = "http://localhost:8000/detect",
        det_size: Tuple[int, int] = (320, 320),
        model_name: str = "buffalo_s",
        timeout: float = 5.0,
        fallback_to_local: bool = True,
        use_gpu: bool = False,
        fast_detector: bool = False,
        api_key: Optional[str] = None,
    ) -> None:
        self.endpoint = endpoint
        self.det_size = det_size
        self.model_name = model_name
        self.timeout = float(timeout)
        self.fallback_to_local = bool(fallback_to_local)
        self.api_key = api_key

        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        self._local_detector: Optional[InsightFaceDetector] = None
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3
        self._last_failure_time = 0.0
        self._cooldown_period = 10.0  # seconds before retrying remote after failure

        if self.fallback_to_local:
            try:
                self._local_detector = InsightFaceDetector(
                    use_gpu=use_gpu,
                    det_size=det_size,
                    model_name=model_name,
                    fast_detector=fast_detector,
                )
                logger.info("Initialized local fallback detector for RemoteInsightFaceDetector")
            except Exception as e:
                logger.warning(f"Could not initialize local fallback detector: {e}")

    def _should_use_local(self) -> bool:
        if not self.fallback_to_local or self._local_detector is None:
            return False
        if self._consecutive_failures >= self._max_consecutive_failures:
            if time.time() - self._last_failure_time < self._cooldown_period:
                return True
            # Cooldown expired, try remote again
            self._consecutive_failures = 0
        return False

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Detect faces either via remote endpoint or local fallback."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return []

        if self._should_use_local():
            return self._local_detector.detect(frame)

        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError("Failed to encode frame as JPEG")

            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            files = {"file": ("frame.jpg", buf.tobytes(), "image/jpeg")}
            response = self._session.post(
                self.endpoint,
                files=files,
                headers=headers,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                self._consecutive_failures = 0
                data = response.json()
                remote_detections = data.get("detections", [])
                results: List[Dict[str, Any]] = []

                for det in remote_detections:
                    bbox = det.get("bbox", [0, 0, 0, 0])
                    res_item: Dict[str, Any] = {
                        "bbox": [int(v) for v in bbox],
                        "det_score": float(det.get("confidence", 1.0)),
                        "gender": det.get("gender"),
                        "age": det.get("age"),
                    }
                    if det.get("embedding"):
                        res_item["embedding"] = np.asarray(det["embedding"], dtype=np.float32)
                    results.append(res_item)
                return results

            raise RuntimeError(f"Remote returned HTTP {response.status_code}: {response.text}")

        except Exception as e:
            self._consecutive_failures += 1
            self._last_failure_time = time.time()
            logger.warning(
                f"Remote detector request failed ({self._consecutive_failures}/{self._max_consecutive_failures}): {e}"
            )
            if self.fallback_to_local and self._local_detector is not None:
                return self._local_detector.detect(frame)
            return []

    def extract_embedding(self, frame: np.ndarray, face_dict: Dict[str, Any]) -> Optional[np.ndarray]:
        """Extract embedding from face dict (cached from remote) or fallback to local."""
        if "embedding" in face_dict and face_dict["embedding"] is not None:
            return np.asarray(face_dict["embedding"], dtype=np.float32)

        if self._local_detector is not None:
            return self._local_detector.extract_embedding(frame, face_dict)
        return None

    def close(self) -> None:
        """Release underlying HTTP session."""
        try:
            self._session.close()
        except Exception:
            pass
