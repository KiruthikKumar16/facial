"""
PC Frame Sender for Distributed Facial Recognition
Captures video locally and sends frames to a remote detection service (e.g., Google Colab).
Optionally draws detection results locally for preview.
"""
import cv2
import requests
import json
import time
from pathlib import Path
import numpy as np
from typing import Optional, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PCFrameSender:
    def __init__(self,
                 remote_url: str,
                 api_key: str,
                 camera_source: str = "webcam",
                 webcam_index: int = 0,
                 rtsp_urls: Optional[list] = None,
                 frame_width: int = 640,
                 frame_height: int = 480,
                 fps: int = 10,
                 show_preview: bool = True,
                 preview_width: int = 640,
                 preview_height: int = 480):
        """
        Initialize the PC frame sender.

        Args:
            remote_url: URL of the remote detection service (e.g., https://xxxx.ngrok.io/detect)
            api_key: API key for authenticating with the remote service
            camera_source: "webcam" or "rtsp"
            webcam_index: Index for webcam if camera_source is webcam
            rtsp_urls: List of RTSP URLs if camera_source is rtsp (will use first)
            frame_width: Width to resize frames for sending (detection size)
            frame_height: Height to resize frames for sending
            fps: Target FPS for sending frames
            show_preview: Whether to show local preview with drawn detections
            preview_width: Width for preview window
            preview_height: Height for preview window
        """
        self.remote_url = remote_url.rstrip('/')
        self.api_key = api_key
        self.camera_source = camera_source
        self.webcam_index = webcam_index
        self.rtsp_urls = rtsp_urls or []
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.fps = fps
        self.show_preview = show_preview
        self.preview_width = preview_width
        self.preview_height = preview_height

        # Initialize video capture
        self.cap = None
        self._init_capture()

        # Frame timing
        self.frame_delay = 1.0 / fps if fps > 0 else 0
        self.last_frame_time = 0

        # Statistics
        self.frames_sent = 0
        self.detections_received = 0
        self.errors = 0

    def _init_capture(self):
        """Initialize video capture based on source."""
        if self.camera_source == "webcam":
            self.cap = cv2.VideoCapture(self.webcam_index)
            if not self.cap.isOpened():
                raise RuntimeError(f"Could not open webcam index {self.webcam_index}")
            # Set capture size (optional, we'll resize later)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            logger.info(f"Initialized webcam {self.webcam_index}")
        elif self.camera_source == "rtsp":
            if not self.rtsp_urls:
                raise ValueError("RTSP URLs must be provided for rtsp camera source")
            # Try each URL until one works
            for url in self.rtsp_urls:
                self.cap = cv2.VideoCapture(url)
                if self.cap.isOpened():
                    logger.info(f"Opened RTSP stream: {url}")
                    break
                else:
                    logger.warning(f"Failed to open RTSP stream: {url}")
            if not self.cap or not self.cap.isOpened():
                raise RuntimeError("Could not open any RTSP stream")
        else:
            raise ValueError(f"Unsupported camera source: {self.camera_source}")

    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a frame from the video source."""
        if not self.cap or not self.cap.isOpened():
            logger.error("Video capture not initialized or closed")
            return None

        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to capture frame")
            return None

        # Resize to detection dimensions if needed
        if frame.shape[1] != self.frame_width or frame.shape[0] != self.frame_height:
            frame = cv2.resize(frame, (self.frame_width, self.frame_height))

        return frame

    def _encode_frame(self, frame: np.ndarray) -> bytes:
        """Encode frame as JPEG for transmission."""
        # Encode as JPEG with reasonable quality
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        result, encoded_img = cv2.imencode('.jpg', frame, encode_param)
        if not result:
            raise RuntimeError("Failed to encode frame as JPEG")
        return encoded_img.tobytes()

    def _send_frame(self, frame_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Send frame to remote detection service and return results."""
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "image/jpeg"
        }
        try:
            start_time = time.time()
            response = requests.post(
                f"{self.remote_url}/detect",
                data=frame_bytes,
                headers=headers,
                timeout=10  # 10 second timeout
            )
            elapsed = time.time() - start_time
            logger.debug(f"Frame sent in {elapsed:.2f}s, status: {response.status_code}")

            if response.status_code == 200:
                self.frames_sent += 1
                return response.json()
            else:
                logger.error(f"Remote service error: {response.status_code} - {response.text}")
                self.errors += 1
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            self.errors += 1
            return None

    def _draw_detections(self, frame: np.ndarray, detections: list) -> np.ndarray:
        """Draw detection results on frame for preview."""
        if not detections:
            return frame

        # Create a copy to draw on
        display_frame = frame.copy()

        for det in detections:
            # Expect detection format: {
            #   "bbox": [x0, y0, x1, y1],
            #   "identity": str,
            #   "confidence": float,
            #   ... other fields
            # }
            bbox = det.get("bbox")
            identity = det.get("identity", "Unknown")
            confidence = det.get("confidence", 0.0)

            if bbox and len(bbox) == 4:
                x0, y0, x1, y1 = map(int, bbox)
                # Draw bounding box
                color = (0, 255, 0) if identity != "Unknown" else (0, 0, 255)
                cv2.rectangle(display_frame, (x0, y0), (x1, y1), color, 2)

                # Draw label
                label = f"{identity}: {confidence:.2f}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                label_y = y0 - 10 if y0 - 10 > 10 else y0 + 10
                cv2.rectangle(display_frame,
                             (x0, label_y - label_size[1] - 10),
                             (x0 + label_size[0], label_y + 5),
                             color, -1)
                cv2.putText(display_frame, label,
                           (x0, label_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                           (255, 255, 255), 2)

        return display_frame

    def run(self):
        """Main loop: capture frames, send to remote service, handle results."""
        logger.info("Starting PC frame sender...")
        logger.info(f"Remote URL: {self.remote_url}")
        logger.info(f"Camera source: {self.camera_source}")
        logger.info(f"Target FPS: {self.fps}")

        try:
            while True:
                # Frame rate limiting
                if self.fps > 0:
                    elapsed = time.time() - self.last_frame_time
                    if elapsed < self.frame_delay:
                        time.sleep(self.frame_delay - elapsed)

                # Capture frame
                frame = self._capture_frame()
                if frame is None:
                    logger.warning("Skipping frame due to capture failure")
                    continue

                # Encode and send
                frame_bytes = self._encode_frame(frame)
                result = self._send_frame(frame_bytes)

                # Update timing
                self.last_frame_time = time.time()

                # Handle result
                if result:
                    self.detections_received += 1
                    detections = result.get("detections", [])

                    # Show preview if enabled
                    if self.show_preview:
                        display_frame = self._draw_detections(frame, detections)
                        # Resize for preview if needed
                        if display_frame.shape[1] != self.preview_width or display_frame.shape[0] != self.preview_height:
                            display_frame = cv2.resize(display_frame,
                                                     (self.preview_width, self.preview_height))
                        cv2.imshow("PC Frame Sender - Preview", display_frame)

                        # Check for exit key
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q') or key == 27:  # q or ESC
                            logger.info("Exit key pressed")
                            break
                    else:
                        # Still need to call waitKey to allow OpenCV to process events
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q') or key == 27:
                            logger.info("Exit key pressed")
                            break
                else:
                    # If we failed to get a result, still show the raw frame if preview enabled
                    if self.show_preview:
                        display_frame = frame.copy()
                        if display_frame.shape[1] != self.preview_width or display_frame.shape[0] != self.preview_height:
                            display_frame = cv2.resize(display_frame,
                                                     (self.preview_width, self.preview_height))
                        cv2.imshow("PC Frame Sender - Preview", display_frame)
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q') or key == 27:
                            logger.info("Exit key pressed")
                            break

                # Log statistics periodically
                if self.frames_sent % 100 == 0 and self.frames_sent > 0:
                    logger.info(f"Stats - Sent: {self.frames_sent}, "
                               f"Received: {self.detections_received}, "
                               f"Errors: {self.errors}")

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            self.cleanup()

    def cleanup(self):
        """Release resources."""
        logger.info("Cleaning up...")
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        logger.info(f"Final stats - Sent: {self.frames_sent}, "
                   f"Received: {self.detections_received}, "
                   f"Errors: {self.errors}")

def main():
    """Example usage - replace with your actual configuration."""
    # IMPORTANT: Replace these with your actual values
    REMOTE_URL = "https://your-colab-tunnel.ngrok.io"  # e.g., https://xxxx.ngrok.io
    API_KEY = "your-edge-api-key-here"  # Must match what your Colab service expects

    # You can also load from config file or environment variables
    sender = PCFrameSender(
        remote_url=REMOTE_URL,
        api_key=API_KEY,
        camera_source="webcam",  # or "rtsp"
        webcam_index=0,
        # rtsp_urls=["rtsp://192.168.1.73:8080/h264.sdp"],  # if using RTSP
        frame_width=640,
        frame_height=640,
        fps=5,  # Adjust based on your network and Colab performance
        show_preview=True,
        preview_width=640,
        preview_height=480
    )

    sender.run()

if __name__ == "__main__":
    main()