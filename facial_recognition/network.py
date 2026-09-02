import time
import collections
from typing import Dict, Any

class NetworkState:
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"

class NetworkMonitor:
    """Monitors network latency, failure rate, and throughput without heavy overhead."""
    
    def __init__(
        self,
        window_size: int = 20,
        degraded_latency_ms: float = 1000.0,
        degraded_failure_rate: float = 0.05,
        offline_failure_rate: float = 0.50
    ):
        self.window_size = window_size
        self.degraded_latency_ms = degraded_latency_ms
        self.degraded_failure_rate = degraded_failure_rate
        self.offline_failure_rate = offline_failure_rate
        
        self._history = collections.deque(maxlen=window_size)
        self._ema_latency_ms = 0.0
        self._ema_alpha = 0.2
        
        self.total_bytes_sent = 0
        self.total_events_sent = 0
        self.total_requests = 0

    def record_request(self, success: bool, latency_ms: float, bytes_sent: int = 0, events_sent: int = 0) -> None:
        """Record a network request attempt."""
        self._history.append(success)
        
        if success:
            if self._ema_latency_ms == 0.0:
                self._ema_latency_ms = latency_ms
            else:
                self._ema_latency_ms = (self._ema_alpha * latency_ms) + ((1 - self._ema_alpha) * self._ema_latency_ms)
                
            self.total_bytes_sent += bytes_sent
            self.total_events_sent += events_sent
            self.total_requests += 1

    def get_failure_rate(self) -> float:
        """Calculate recent failure rate."""
        if not self._history:
            return 0.0
        failures = sum(1 for success in self._history if not success)
        return failures / len(self._history)

    def get_state(self) -> str:
        """Determine current network state based on history."""
        failure_rate = self.get_failure_rate()
        
        if failure_rate >= self.offline_failure_rate:
            return NetworkState.OFFLINE
            
        if failure_rate >= self.degraded_failure_rate or self._ema_latency_ms >= self.degraded_latency_ms:
            return NetworkState.DEGRADED
            
        return NetworkState.GOOD

    def get_metrics(self) -> Dict[str, Any]:
        """Get network metrics."""
        bytes_per_event = (self.total_bytes_sent / self.total_events_sent) if self.total_events_sent > 0 else 0
        events_per_request = (self.total_events_sent / self.total_requests) if self.total_requests > 0 else 0
        
        return {
            "network_state": self.get_state(),
            "average_latency_ms": round(self._ema_latency_ms, 2),
            "recent_failure_rate": round(self.get_failure_rate(), 3),
            "bytes_per_event": round(bytes_per_event, 2),
            "events_per_request": round(events_per_request, 2),
            "total_bytes_sent": self.total_bytes_sent,
            "total_requests": self.total_requests
        }
