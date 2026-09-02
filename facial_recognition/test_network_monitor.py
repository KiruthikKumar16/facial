import pytest
from facial_recognition.network import NetworkMonitor, NetworkState

def test_network_monitor_good_state():
    monitor = NetworkMonitor()
    for _ in range(10):
        monitor.record_request(True, 100.0, bytes_sent=1000, events_sent=10)
        
    assert monitor.get_state() == NetworkState.GOOD
    metrics = monitor.get_metrics()
    assert metrics["average_latency_ms"] == 100.0
    assert metrics["recent_failure_rate"] == 0.0
    assert metrics["bytes_per_event"] == 100.0
    assert metrics["events_per_request"] == 10.0

def test_network_monitor_degraded_latency():
    monitor = NetworkMonitor(degraded_latency_ms=500.0)
    for _ in range(10):
        monitor.record_request(True, 600.0)
        
    assert monitor.get_state() == NetworkState.DEGRADED

def test_network_monitor_degraded_failure_rate():
    monitor = NetworkMonitor(degraded_failure_rate=0.1)
    
    # 8 successes, 2 failures -> 20% failure rate
    for _ in range(8):
        monitor.record_request(True, 100.0)
    for _ in range(2):
        monitor.record_request(False, 1000.0)
        
    assert monitor.get_state() == NetworkState.DEGRADED
    assert monitor.get_failure_rate() == 0.2

def test_network_monitor_offline():
    monitor = NetworkMonitor(offline_failure_rate=0.5)
    
    # 4 successes, 6 failures -> 60% failure rate
    for _ in range(4):
        monitor.record_request(True, 100.0)
    for _ in range(6):
        monitor.record_request(False, 1000.0)
        
    assert monitor.get_state() == NetworkState.OFFLINE
    assert monitor.get_failure_rate() == 0.6

def test_network_monitor_recovery():
    monitor = NetworkMonitor(offline_failure_rate=0.5)
    
    for _ in range(10):
        monitor.record_request(False, 1000.0)
    assert monitor.get_state() == NetworkState.OFFLINE
    
    # Recover
    for _ in range(20):
        monitor.record_request(True, 100.0)
        
    assert monitor.get_state() == NetworkState.GOOD
