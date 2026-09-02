"""
Camera Topology Graph for Cross-Camera Continuity Tracking.

Models cameras as nodes and physical pathways/transitions as directed edges with
associated travel time windows, physical distances, and transition priors.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CameraNode:
    """Represents a camera node in the physical topology."""
    camera_id: str
    name: str = ""
    zone: str = ""
    location_description: str = ""
    coordinates: Optional[Tuple[float, float]] = None  # (x, y) or (lat, lon)


@dataclass
class CameraEdge:
    """Represents an allowed physical transition from one camera to another."""
    from_camera_id: str
    to_camera_id: str
    min_travel_seconds: float = 2.0     # Minimum physically plausible travel time (teleportation threshold)
    max_travel_seconds: float = 120.0   # Maximum expected continuity window
    typical_travel_seconds: float = 15.0 # Expected / average travel time
    distance_meters: float = 10.0       # Physical distance in meters
    transition_probability: float = 1.0 # Prior transition likelihood / weight
    bidirectional: bool = False         # Helper flag during edge creation


class CameraTopologyGraph:
    """
    Directed graph representing camera connectivity, physical constraints,
    and expected travel times between cameras in a facility.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, CameraNode] = {}
        # adjacency: from_camera_id -> {to_camera_id: CameraEdge}
        self.edges: Dict[str, Dict[str, CameraEdge]] = {}

    def add_node(
        self,
        camera_id: str,
        name: str = "",
        zone: str = "",
        location_description: str = "",
        coordinates: Optional[Tuple[float, float]] = None,
    ) -> CameraNode:
        """Add or update a camera node."""
        node = CameraNode(
            camera_id=camera_id,
            name=name or camera_id,
            zone=zone,
            location_description=location_description,
            coordinates=coordinates,
        )
        self.nodes[camera_id] = node
        if camera_id not in self.edges:
            self.edges[camera_id] = {}
        return node

    def add_edge(
        self,
        from_camera_id: str,
        to_camera_id: str,
        min_travel_seconds: float = 2.0,
        max_travel_seconds: float = 120.0,
        typical_travel_seconds: float = 15.0,
        distance_meters: float = 10.0,
        transition_probability: float = 1.0,
        bidirectional: bool = False,
    ) -> CameraEdge:
        """Add an allowed transition edge between two cameras."""
        # Ensure nodes exist
        if from_camera_id not in self.nodes:
            self.add_node(from_camera_id)
        if to_camera_id not in self.nodes:
            self.add_node(to_camera_id)

        edge = CameraEdge(
            from_camera_id=from_camera_id,
            to_camera_id=to_camera_id,
            min_travel_seconds=float(min_travel_seconds),
            max_travel_seconds=float(max_travel_seconds),
            typical_travel_seconds=float(typical_travel_seconds),
            distance_meters=float(distance_meters),
            transition_probability=float(transition_probability),
            bidirectional=bidirectional,
        )
        self.edges[from_camera_id][to_camera_id] = edge

        if bidirectional:
            reverse_edge = CameraEdge(
                from_camera_id=to_camera_id,
                to_camera_id=from_camera_id,
                min_travel_seconds=float(min_travel_seconds),
                max_travel_seconds=float(max_travel_seconds),
                typical_travel_seconds=float(typical_travel_seconds),
                distance_meters=float(distance_meters),
                transition_probability=float(transition_probability),
                bidirectional=True,
            )
            self.edges[to_camera_id][from_camera_id] = reverse_edge

        return edge

    def remove_edge(self, from_camera_id: str, to_camera_id: str) -> bool:
        """Remove a transition edge."""
        if from_camera_id in self.edges and to_camera_id in self.edges[from_camera_id]:
            del self.edges[from_camera_id][to_camera_id]
            return True
        return False

    def get_edge(self, from_camera_id: str, to_camera_id: str) -> Optional[CameraEdge]:
        """Get direct transition edge between two cameras if it exists."""
        if from_camera_id == to_camera_id:
            # Self-transition (co-located observation on the same camera)
            return CameraEdge(
                from_camera_id=from_camera_id,
                to_camera_id=to_camera_id,
                min_travel_seconds=0.0,
                max_travel_seconds=30.0,
                typical_travel_seconds=1.0,
                distance_meters=0.0,
                transition_probability=1.0,
            )
        return self.edges.get(from_camera_id, {}).get(to_camera_id)

    def is_transition_allowed(self, from_camera_id: str, to_camera_id: str) -> bool:
        """Check if a direct transition is allowed in the topology."""
        if from_camera_id == to_camera_id:
            return True
        return to_camera_id in self.edges.get(from_camera_id, {})

    def get_reachable_cameras(
        self,
        from_camera_id: str,
        elapsed_seconds: float,
        include_multihop: bool = True,
        max_hops: int = 3,
    ) -> List[Tuple[str, float, Optional[CameraEdge]]]:
        """
        Get all cameras reachable from from_camera_id within elapsed_seconds.
        
        Returns:
            List of (camera_id, temporal_plausibility_score, direct_edge_or_none)
        """
        if from_camera_id not in self.nodes and from_camera_id not in self.edges:
            return []

        results: List[Tuple[str, float, Optional[CameraEdge]]] = []

        # 1. Direct neighbors
        for neighbor_id, edge in self.edges.get(from_camera_id, {}).items():
            if edge.min_travel_seconds <= elapsed_seconds <= edge.max_travel_seconds:
                # Temporal plausibility score: 1.0 at typical time, smoothly decaying toward boundaries
                score = self.compute_temporal_score(elapsed_seconds, edge)
                results.append((neighbor_id, score, edge))

        # 2. Multi-hop reachability if requested and time permits
        if include_multihop and max_hops > 1:
            visited: Set[str] = {from_camera_id} | {r[0] for r in results}
            # (current_node, total_min_time, total_max_time, hops)
            queue: List[Tuple[str, float, float, int]] = []
            for n_id, edge in self.edges.get(from_camera_id, {}).items():
                queue.append((n_id, edge.min_travel_seconds, edge.max_travel_seconds, 1))

            while queue:
                curr, min_t, max_t, hops = queue.pop(0)
                if hops >= max_hops:
                    continue

                for next_id, next_edge in self.edges.get(curr, {}).items():
                    if next_id in visited:
                        continue
                    cum_min = min_t + next_edge.min_travel_seconds
                    cum_max = max_t + next_edge.max_travel_seconds
                    if cum_min <= elapsed_seconds <= cum_max:
                        synthetic_edge = CameraEdge(
                            from_camera_id=from_camera_id,
                            to_camera_id=next_id,
                            min_travel_seconds=cum_min,
                            max_travel_seconds=cum_max,
                            typical_travel_seconds=(cum_min + cum_max) / 2.0,
                            distance_meters=100.0 * hops,
                            transition_probability=0.5 ** hops,
                        )
                        score = self.compute_temporal_score(elapsed_seconds, synthetic_edge) * (0.8 ** hops)
                        results.append((next_id, score, synthetic_edge))
                        visited.add(next_id)

                    if cum_min <= elapsed_seconds:
                        queue.append((next_id, cum_min, cum_max, hops + 1))

        # Sort by plausibility score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    @staticmethod
    def compute_temporal_score(elapsed_seconds: float, edge: CameraEdge) -> float:
        """
        Compute a normalized temporal plausibility score in [0.0, 1.0].
        Score is 1.0 near typical_travel_seconds, decreasing toward min and max limits.
        Returns 0.0 if outside [min_travel_seconds, max_travel_seconds].
        """
        if elapsed_seconds < edge.min_travel_seconds:
            return 0.0
        if elapsed_seconds > edge.max_travel_seconds:
            return 0.0

        typical = edge.typical_travel_seconds
        if elapsed_seconds <= typical:
            span = max(0.001, typical - edge.min_travel_seconds)
            # Ramps up from 0.5 at min_travel to 1.0 at typical
            return 0.5 + 0.5 * ((elapsed_seconds - edge.min_travel_seconds) / span)
        else:
            span = max(0.001, edge.max_travel_seconds - typical)
            # Decays from 1.0 at typical to 0.2 at max_travel
            return 1.0 - 0.8 * ((elapsed_seconds - typical) / span)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize topology graph to dictionary."""
        nodes_data = {k: asdict(v) for k, v in self.nodes.items()}
        edges_data = []
        for from_id, targets in self.edges.items():
            for to_id, edge in targets.items():
                edges_data.append(asdict(edge))
        return {
            "nodes": nodes_data,
            "edges": edges_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CameraTopologyGraph:
        """Deserialize topology graph from dictionary."""
        graph = cls()
        nodes_dict = data.get("nodes", {})
        for cam_id, n_data in nodes_dict.items():
            graph.add_node(
                camera_id=cam_id,
                name=n_data.get("name", ""),
                zone=n_data.get("zone", ""),
                location_description=n_data.get("location_description", ""),
                coordinates=tuple(n_data["coordinates"]) if n_data.get("coordinates") else None,
            )

        edges_list = data.get("edges", [])
        for e in edges_list:
            graph.add_edge(
                from_camera_id=e["from_camera_id"],
                to_camera_id=e["to_camera_id"],
                min_travel_seconds=e.get("min_travel_seconds", 2.0),
                max_travel_seconds=e.get("max_travel_seconds", 120.0),
                typical_travel_seconds=e.get("typical_travel_seconds", 15.0),
                distance_meters=e.get("distance_meters", 10.0),
                transition_probability=e.get("transition_probability", 1.0),
                bidirectional=e.get("bidirectional", False),
            )
        return graph

    def save_to_file(self, filepath: str | Path) -> None:
        """Save topology graph to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str | Path) -> CameraTopologyGraph:
        """Load topology graph from a JSON file."""
        path = Path(filepath)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
