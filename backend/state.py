import asyncio
import dataclasses
from typing import Dict, Any, Optional

try:
    from facial_recognition.topology import CameraTopologyGraph
    from facial_recognition.cross_camera_tracker import CrossCameraContinuityTracker
    from facial_recognition.version_bundle import ModelConfigVersionBundle
except ImportError:
    CameraTopologyGraph = None
    CrossCameraContinuityTracker = None
    ModelConfigVersionBundle = None

# Global state for AI models and camera pipelines
ai_models: Dict[str, Any] = {}

# camera_id -> CameraPipeline
camera_pipelines: Dict[str, Any] = {}

# Initialize global topology graph and cross-camera tracker
topology_graph = CameraTopologyGraph() if CameraTopologyGraph else None
continuity_tracker = CrossCameraContinuityTracker(topology_graph=topology_graph) if CrossCameraContinuityTracker else None
active_version_bundle = ModelConfigVersionBundle() if ModelConfigVersionBundle else None

# ---------- Frame relay store ----------
# camera_id -> latest raw JPEG bytes pushed by the edge node.
@dataclasses.dataclass
class _FrameSlot:
    jpeg: bytes = b""
    event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)

# Populated lazily; access only from the event-loop thread.
_frame_store: Dict[str, _FrameSlot] = {}

def get_frame_slot(camera_id: str) -> _FrameSlot:
    if camera_id not in _frame_store:
        _frame_store[camera_id] = _FrameSlot()
    return _frame_store[camera_id]
