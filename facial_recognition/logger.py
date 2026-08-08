import csv
import os
import threading
from datetime import datetime


class DetectionLogger:
    def __init__(self, log_path: str) -> None:
        self.log_path = log_path
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(log_path)) or '.', exist_ok=True)
        self.file = open(log_path, 'a', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(
            self.file,
            fieldnames=['timestamp', 'camera_id', 'bbox', 'identity', 'confidence'],
        )
        if self.file.tell() == 0:
            self.writer.writeheader()
            self.file.flush()

    def log_detection(self, camera_id: str, bbox: list[int], identity: str, confidence: float) -> None:
        row = {
            'timestamp': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
            'camera_id': camera_id,
            'bbox': f'[{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]',
            'identity': identity,
            'confidence': f'{confidence:.4f}',
        }
        with self.lock:
            self.writer.writerow(row)
            self.file.flush()
        print(
            f"[{row['timestamp']}] {camera_id} {row['bbox']} -> {identity} ({confidence:.4f})"
        )

    def close(self) -> None:
        with self.lock:
            try:
                self.file.close()
            except Exception:
                pass
