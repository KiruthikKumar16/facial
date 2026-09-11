"""
Remote detector for facial recognition that sends frames to a remote service
for face detection and embedding extraction.
"""
import json
import time
import logging
import numpy as np
import cv2
import requests
from typing import Any, Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class RemoteInsightFaceDetector:
    """
    A detector that sends images to a remote HTTP service for face detection
    and embedding extraction, mimicking the interface of InsightFaceDetector.
    """

    def __init__(
        self,
        endpoint: str,
        det_size: Tuple[int, int] = (640, 640),
        model_name: str = 'buffalo_s',
        timeout: float = 5.0,
        fallback_to_local: bool = True,
    ) -> None:
        """
        Initialize the remote detector.

        Args:
            endpoint: URL of the remote detection service (e.g., "http://localhost:8000/detect")
            det_size: Size to which frames are resized before sending to remote (width, height)
            model_name: Name of the model (for logging/compatibility, not used remotely)
            timeout: HTTP request timeout in seconds
            fallback_to_local: If True, fall back to local detector on connection failure
        """
        self.endpoint = endpoint.rstrip('/')
        self.det_size = det_size
        self.model_name = model_name
        self.timeout = timeout
        self.fallback_to_local = fallback_to_local
        self.local_detector = None  # Lazy-loaded if fallback is enabled

        # Cache for the last detection result to avoid sending the same frame twice
        # for detect and extract_embedding calls in the same frame.
        self._last_frame: Optional[np.ndarray] = None
        self._last_results: Optional[List[Dict]] = None

        logger.info(f"RemoteInsightFaceDetector initialized with endpoint: {endpoint}")

    def _load_local_detector(self) -> Any:
        """Lazy load the local detector if needed for fallback."""
        if self.local_detector is None:
            try:
                from detector import InsightFaceDetector
                self.local_detector = InsightFaceDetector(
                    use_gpu=False,  # Assume CPU for fallback
                    det_size=self.det_size,
                    model_name=self.model_name,
                    fast_detector=False
                )
                logger.info("Loaded local detector for fallback")
            except Exception as e:
                logger.error(f"Failed to load local detector for fallback: {e}")
                self.local_detector = None
        return self.local_detector

    def _encode_image(self, img: np.ndarray) -> bytes:
        """Encode image as JPEG for HTTP transmission."""
        # Encode as JPEG with reasonable quality
        _, encoded_img = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return encoded_img.tobytes()

    def _call_remote_service(self, img: np.ndarray) -> Optional[List[Dict]]:
        """
        Send image to remote service and get detection results.

        Returns:
            List of face dictionaries with keys:
                - bbox: [x1, y1, x2, y2] in the coordinates of the input image
                - det_score: confidence score
                - kps: list of 5 keypoints (optional)
                - embedding: 512-dimensional face embedding (optional)
            Returns None if the request fails.
        """
        try:
            # Resize image to the detection size if needed
            if img.shape[1] != self.det_size[0] or img.shape[0] != self.det_size[1]:
                img_to_send = cv2.resize(img, self.det_size, interpolation=cv2.INTER_LINEAR)
            else:
                img_to_send = img

            # Encode image
            jpeg_data = self._encode_image(img_to_send)

            # Prepare request
            files = {'image': ('frame.jpg', jpeg_data, 'image/jpeg')}
            data = {
                'return_embedding': 'true',
                'return_landmarks': 'true'
            }

            # Send request
            response = requests.post(
                self.endpoint,
                files=files,
                data=data,
                timeout=self.timeout
            )
            response.raise_for_status()

            # Parse response
            result = response.json()
            if 'faces' not in result:
                logger.error("Remote service response missing 'faces' key")
                return None

            faces = result['faces']
            logger.debug(f"Remote service returned {len(faces)} faces")
            return faces

        except requests.exceptions.RequestException as e:
            logger.warning(f"Remote service request failed: {e}")
            return None
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse remote service response: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling remote service: {e}")
            return None

    def detect(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect faces in an image.

        Mimics the interface of InsightFaceDetector.detect():
        Returns a list of dictionaries, each containing:
            - 'bbox': tuple (left, top, right, bottom)
            - 'det_score': confidence score
        """
        # Check if we have cached results for this exact frame (unlikely but possible)
        if self._last_frame is not None and np.array_equal(self._last_frame, img):
            if self._last_results is not None:
                logger.debug("Using cached detection results")
                # Return only bbox and det_score to match local detector interface
                return [
                    {
                        'bbox': tuple(face['bbox']),
                        'det_score': face['det_score']
                    }
                    for face in self._last_results
                ]

        # Call remote service
        remote_result = self._call_remote_service(img)

        if remote_result is not None:
            # Cache results
            self._last_frame = img.copy()
            self._last_results = remote_result

            # Convert to expected format
            detections = []
            for face in remote_result:
                # Ensure bbox is a tuple of ints
                bbox = tuple([int(coord) for coord in face['bbox']])
                detections.append({
                    'bbox': bbox,
                    'det_score': float(face.get('det_score', 1.0))
                })
            logger.debug(f"Detected {len(detections)} faces via remote service")
            return detections

        # Fallback to local detector if enabled and available
        if self.fallback_to_local:
            logger.warning("Falling back to local detector")
            local_detector = self._load_local_detector()
            if local_detector is not None:
                return local_detector.detect(img)
            else:
                logger.error("Local detector not available for fallback")
                return []
        else:
            logger.error("Remote service unavailable and fallback disabled")
            return []

    def extract_embedding(self, img: np.ndarray, face: Dict[str, Any]) -> Optional[np.ndarray]:
        """
        Extract embedding for a detected face.

        Args:
            img: The original image (same as passed to detect)
            face: Face dictionary from detect() containing 'bbox' and 'det_score'

        Returns:
            Embedding vector as numpy array, or None if extraction fails
        """
        # Check if we have cached results that include this face
        if self._last_results is not None and self._last_frame is not None:
            # We need to match the face to our cached results.
            # Since we don't have a face ID, we'll assume the order is the same
            # and that the caller is requesting embeddings in the same order
            # as the detections were returned.
            # This is a simplification - in practice we might need to match by bbox.
            # For now, we'll return the embedding for the face at the same index
            # if we can determine the index.

            # Find the index of this face in our last detections by matching bbox
            # (since the pipeline passes the face dict from detect, we can match)
            target_bbox = face['bbox']
            for i, cached_face in enumerate(self._last_results):
                cached_bbox = tuple([int(coord) for coord in cached_face['bbox']])
                if cached_bbox == target_bbox:
                    if 'embedding' in cached_face:
                        embedding = np.array(cached_face['embedding'], dtype=np.float32)
                        logger.debug(f"Using cached embedding for face {i}")
                        return embedding
                    else:
                        logger.warning("Cached face missing embedding")
                        break

        # If we don't have a cached embedding, we need to call the remote service again
        # but this time we could optimize by sending just the face chip.
        # However, for simplicity, we'll resend the whole image and hope for caching
        # or fall back to local.

        logger.warning("No cached embedding available, attempting remote call for embedding")
        remote_result = self._call_remote_service(img)

        if remote_result is not None:
            # Update cache
            self._last_frame = img.copy()
            self._last_results = remote_result

            # Try to find the face again
            target_bbox = face['bbox']
            for cached_face in remote_result:
                cached_bbox = tuple([int(coord) for coord in cached_face['bbox']])
                if cached_bbox == target_bbox:
                    if 'embedding' in cached_face:
                        return np.array(cached_face['embedding'], dtype=np.float32)

        # Fallback to local detector for embedding extraction
        if self.fallback_to_local:
            logger.warning("Falling back to local detector for embedding extraction")
            local_detector = self._load_local_detector()
            if local_detector is not None:
                return local_detector.extract_embedding(img, face)
            else:
                logger.error("Local detector not available for fallback")
                return None
        else:
            logger.error("Remote service unavailable and fallback disabled for embedding")
            return None

    def warmup(self) -> None:
        """Warm up the remote service by sending a dummy request."""
        try:
            # Create a dummy image
            dummy_img = np.zeros((self.det_size[1], self.det_size[0], 3), dtype=np.uint8)
            self._call_remote_service(dummy_img)
            logger.info("Remote service warmup completed")
        except Exception as e:
            logger.warning(f"Remote service warmup failed: {e}")


# For testing purposes
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    # Example usage
    detector = RemoteInsightFaceDetector(
        endpoint="http://localhost:8000/detect",
        det_size=(640, 640),
        fallback_to_local=True
    )

    # Try to detect on a dummy image
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(dummy_img)
    print(f"Detections: {detections}")

    if detections:
        embedding = detector.extract_embedding(dummy_img, detections[0])
        print(f"Embedding shape: {embedding.shape if embedding is not None else None}")