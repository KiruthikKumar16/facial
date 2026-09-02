"""
Edge Camera Configuration Manager with Local Caching, Versioning, and Offline Resiliency.

Maintains per-camera recognition profiles, caches configurations locally,
fetches updates from the cloud when online, and continues operating using
the last known configuration during network outages.
"""

from __future__ import annotations
import json
import logging
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CameraConfigProfile:
    """Active recognition parameter profile for a specific camera."""
    camera_id: str
    version: int = 1
    detection_threshold: float = 0.50
    recognition_threshold: float = 0.35
    quality_thresholds: Optional[Dict[str, Any]] = None
    sampling_rate: int = 1 # Frame skip / sampling rate
    temporal_window: float = 3.0 # Temporal track window in seconds
    notes: Optional[str] = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CameraConfigProfile:
        return cls(
            camera_id=data["camera_id"],
            version=int(data.get("version", 1)),
            detection_threshold=float(data.get("detection_threshold", 0.50)),
            recognition_threshold=float(data.get("recognition_threshold", 0.35)),
            quality_thresholds=data.get("quality_thresholds"),
            sampling_rate=int(data.get("sampling_rate", 1)),
            temporal_window=float(data.get("temporal_window", 3.0)),
            notes=data.get("notes"),
            updated_at=float(data.get("updated_at", time.time())),
        )


class CameraConfigManager:
    """
    Manages per-camera adaptive recognition configurations at the edge.
    Supports persistent disk caching and transparent offline operation.
    """
    def __init__(
        self,
        cache_path: str = "camera_configs_cache.json",
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_config: Optional[Dict[str, Any]] = None,
    ):
        self.cache_path = Path(cache_path)
        self.api_url = (api_url or os.environ.get("API_URL", "http://localhost:8000")).rstrip('/')
        self.api_key = api_key or os.environ.get("EDGE_API_KEY", "default-dev-key")
        self.default_config = default_config or {}

        # In-memory configuration profiles: camera_id -> CameraConfigProfile
        self.profiles: Dict[str, CameraConfigProfile] = {}

        # 1. Load from persistent local disk cache (Offline First)
        self._load_local_cache()

        # 2. Attempt sync from backend if reachable
        self.sync_from_backend()

    def _load_local_cache(self) -> None:
        """Load cached profiles from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for cam_id, profile_dict in data.items():
                        self.profiles[cam_id] = CameraConfigProfile.from_dict(profile_dict)
                logger.info(f"Loaded {len(self.profiles)} camera profiles from local cache ({self.cache_path}).")
            except Exception as e:
                logger.warning(f"Failed to read camera config cache: {e}")

    def _save_local_cache(self) -> None:
        """Persist current profiles to disk cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {cam_id: profile.to_dict() for cam_id, profile in self.profiles.items()}
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self.profiles)} camera profiles to disk cache.")
        except Exception as e:
            logger.error(f"Failed to write camera config cache: {e}")

    def get_profile(self, camera_id: str) -> CameraConfigProfile:
        """
        Get active profile for a camera.
        If camera not yet in cache, initializes default profile (v1) and caches it.
        """
        if camera_id in self.profiles:
            return self.profiles[camera_id]

        # Build initial default profile from fallback config
        q_thresh = self.default_config.get("quality_thresholds")
        sim_thresh = float(self.default_config.get("similarity_threshold", 0.35))
        frame_skip = int(self.default_config.get("cpu_frame_skip", 1))
        track_cfg = self.default_config.get("track_fusion", {})
        temp_win = float(track_cfg.get("max_observation_window_seconds", 3.0))

        profile = CameraConfigProfile(
            camera_id=camera_id,
            version=1,
            detection_threshold=0.50,
            recognition_threshold=sim_thresh,
            quality_thresholds=q_thresh,
            sampling_rate=frame_skip,
            temporal_window=temp_win,
            notes="Default edge initialized profile",
            updated_at=time.time(),
        )
        self.profiles[camera_id] = profile
        self._save_local_cache()
        return profile

    def update_profile(self, profile: CameraConfigProfile) -> None:
        """Update or insert a camera profile and persist."""
        self.profiles[profile.camera_id] = profile
        self._save_local_cache()
        logger.info(f"Updated profile for camera {profile.camera_id} to version {profile.version}")

    def sync_from_backend(self) -> bool:
        """
        Sync active camera configurations from the backend.
        If network is offline or backend unreachable, gracefully preserves local cache.
        """
        endpoint = f"{self.api_url}/api/internal/camera_configs"
        try:
            req = urllib.request.Request(endpoint, headers={"X-API-Key": self.api_key})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    configs_data = json.loads(resp.read().decode("utf-8"))
                    updated_count = 0
                    for c in configs_data:
                        cam_id = c["camera_id"]
                        profile = CameraConfigProfile(
                            camera_id=cam_id,
                            version=int(c.get("version", 1)),
                            detection_threshold=float(c.get("detection_threshold", 0.50)),
                            recognition_threshold=float(c.get("recognition_threshold", 0.35)),
                            quality_thresholds=c.get("quality_thresholds"),
                            sampling_rate=int(c.get("sampling_rate", 1)),
                            temporal_window=float(c.get("temporal_window", 3.0)),
                            notes=c.get("notes"),
                            updated_at=time.time(),
                        )
                        self.profiles[cam_id] = profile
                        updated_count += 1
                    self._save_local_cache()
                    logger.info(f"Synced {updated_count} camera profiles from backend.")
                    return True
        except (urllib.error.URLError, TimeoutError, Exception) as e:
            logger.debug(f"Backend camera config sync skipped/failed (operating offline on cached configs): {e}")
        return False
