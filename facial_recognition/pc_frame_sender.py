"""
PC Frame Sender for Distributed Facial Recognition.
Captures frames from a local webcam or RTSP feed and sends them to a remote
detection service (Google Colab, Kaggle, or GPU server).
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import cv2
import requests

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pc_frame_sender")

# Configuration defaults - override with environment variables or command-line args
REMOTE_URL = os.getenv("REMOTE_DETECTION_URL", "http://localhost:7860").rstrip("/")
API_KEY = os.getenv("COLAB_API_KEY", "")
CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "0")  # Index 0 or RTSP URL
TARGET_FPS = float(os.getenv("TARGET_FPS", "5.0"))
SHOW_PREVIEW = os.getenv("SHOW_PREVIEW", "true").lower() == "true"
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))


def parse_camera_source(source_str: str):
    """Parse camera source string into integer webcam index or RTSP stream URL."""
    try:
        return int(source_str)
    except ValueError:
        return source_str


def main():
    logger.info("Starting PC Frame Sender...")
    logger.info(f"Remote service endpoint: {REMOTE_URL}/detect")
    logger.info(f"Camera source: {CAMERA_SOURCE} | Target FPS: {TARGET_FPS}")

    cap = cv2.VideoCapture(parse_camera_source(CAMERA_SOURCE))
    if not cap.isOpened():
        logger.error(f"Failed to open video source: {CAMERA_SOURCE}")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    frame_interval = 1.0 / max(1.0, TARGET_FPS)
    last_send_time = 0.0
    total_frames = 0
    successful_sends = 0
    last_stats_time = time.time()

    headers = {}
    if API_KEY:
        headers["x-api-key"] = API_KEY

    last_detections: List[Dict[str, Any]] = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Empty frame received from video source.")
                time.sleep(0.1)
                continue

            now = time.time()
            if now - last_send_time >= frame_interval:
                last_send_time = now
                total_frames += 1

                # Encode frame to JPEG
                ok, jpeg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    try:
                        t0 = time.perf_counter()
                        files = {"file": ("frame.jpg", jpeg_buf.tobytes(), "image/jpeg")}
                        response = requests.post(
                            f"{REMOTE_URL}/detect",
                            files=files,
                            headers=headers,
                            timeout=4.0,
                        )
                        req_time = (time.perf_counter() - t0) * 1000.0

                        if response.status_code == 200:
                            successful_sends += 1
                            data = response.json()
                            last_detections = data.get("detections", [])
                            logger.debug(
                                f"Remote detected {len(last_detections)} faces in {req_time:.1f}ms"
                            )
                        else:
                            logger.warning(
                                f"Remote service returned HTTP {response.status_code}: {response.text[:100]}"
                            )
                    except requests.exceptions.RequestException as e:
                        logger.warning(f"Failed to send frame to remote service: {e}")

            # Draw detections overlay on frame
            display_frame = frame.copy()
            h, w = display_frame.shape[:2]

            for det in last_detections:
                bbox = det.get("bbox", [0, 0, 0, 0])
                x0, y0, x1, y1 = max(0, int(bbox[0])), max(0, int(bbox[1])), min(w, int(bbox[2])), min(h, int(bbox[3]))
                identity = det.get("identity", "Unknown")
                conf = float(det.get("confidence", 0.0))
                is_recognized = det.get("status") == "recognized" and not identity.startswith("Person ") and identity != "Unknown"

                color = (0, 255, 0) if is_recognized else (0, 0, 255)
                cv2.rectangle(display_frame, (x0, y0), (x1, y1), color, 2)

                label = f"{identity} ({conf:.2f})"
                (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(display_frame, (x0, max(0, y0 - lh - 6)), (x0 + lw + 6, y0), color, cv2.FILLED)
                cv2.putText(display_frame, label, (x0 + 3, y0 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            # Periodic stats logging
            if now - last_stats_time >= 10.0:
                elapsed = now - last_stats_time
                fps = total_frames / elapsed
                success_rate = (successful_sends / total_frames * 100.0) if total_frames > 0 else 0.0
                logger.info(f"Stats: {fps:.1f} FPS | Success: {success_rate:.0f}% ({successful_sends}/{total_frames})")
                last_stats_time = now
                total_frames = 0
                successful_sends = 0

            # Local preview
            if SHOW_PREVIEW:
                try:
                    cv2.imshow("Remote Detection Preview (Press Q to exit)", display_frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        logger.info("Exit requested by user.")
                        break
                except Exception:
                    # In headless or non-GUI environments, disable preview
                    SHOW_PREVIEW = False

    except KeyboardInterrupt:
        logger.info("Terminating on user interrupt...")
    finally:
        cap.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        logger.info("PC Frame Sender shut down cleanly.")


if __name__ == "__main__":
    main()
