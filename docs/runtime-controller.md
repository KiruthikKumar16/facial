# Edge-Node Health Monitoring & Adaptive Runtime Controller

## 1. Executive Summary
Edge facial-recognition nodes operate under unpredictable, fluctuating environmental and hardware constraints:
- Thermal throttling on embedded NPUs/GPUs or high-ambient outdoor deployments
- Compute saturation during sudden crowd surges
- Network degradation, intermittent cellular/WiFi jitter, or complete link dropouts
- Storage exhaustion on local solid-state flash drives

The **Adaptive Runtime Controller** continuously monitors 11 critical hardware, pipeline throughput, and network metrics. When resource constraints are detected, it dynamically adapts frame sampling rates, batching intervals, and storage priorities using hysteresis threshold bands to prevent rapid mode oscillation (anti-flapping).

---

## 2. Monitored Health Metrics

| Metric | Target / Nominal | Unit | Description |
| :--- | :--- | :--- | :--- |
| **CPU Usage** | $< 70\%$ | `%` | Host CPU utilization percentage |
| **GPU Usage** | $< 80\%$ | `%` | Accelerator / NPU utilization |
| **Memory** | $< 75\%$ | `%` | Host RAM consumption percentage |
| **Temperature** | $< 70^\circ\text{C}$ | $^\circ\text{C}$ | On-die core thermal sensor |
| **Disk Free** | $> 1000\text{ MB}$ | $\text{MB}$ | Available space on local flash storage |
| **Camera FPS** | $\ge 25.0$ | $\text{FPS}$ | Frame acquisition rate from camera RTSP stream |
| **Inference FPS** | $\ge 25.0$ | $\text{FPS}$ | Processed inferences per second |
| **Network Latency** | $< 100\text{ ms}$ | $\text{ms}$ | Round-trip ping/HTTP latency to central backend |
| **Sync Queue Length** | $< 10$ | $\text{count}$ | In-flight detection events awaiting server ACK |
| **Event Backlog** | $0$ | $\text{count}$ | Unsynced persisted events in local SQLite ledger |
| **Recognition Latency** | $< 35\text{ ms}$ | $\text{ms}$ | End-to-end face recognition inference time |

---

## 3. Operational Runtime Modes & Control Actions

```
                               ┌───────────────────────────┐
                               │        NORMAL MODE        │
                               │ - Frame Sampling: 1.0x    │
                               │ - Batch Size: 5 events    │
                               │ - Batch Interval: 1.0s    │
                               └─────────────┬─────────────┘
                                             │
      ┌───────────────────────┬──────────────┼───────────────────────┬───────────────────────┐
      │ CPU > 85%             │ Latency>500ms│ Connection Lost       │ Disk < 500 MB         │
      │ or Rec Latency > 80ms │ (3 cycles)   │ (is_online=False)     │ (1 cycle)             │
      ▼                       ▼              ▼                       ▼                       ▼
┌──────────────────┐  ┌──────────────────┐ ┌──────────────────┐  ┌───────────────────────────────┐
│THROTTLED_COMPUTE │  │ DEGRADED_NETWORK │ │   OFFLINE MODE   │  │   EMERGENCY_DISK_PRESSURE     │
│- Sample: 0.33x   │  │- Batch Size: 25  │ │- Live Sync: OFF  │  │- Purge transient logs/debug   │
│  (1 in 3 frames) │  │- Interval: 5.0s  │ │- Local Buffer: ON│  │- STRICTLY PRESERVE VIP/ALERTS │
│- Prevents crash  │  │- Reduce HTTP RTT │ │- Exponential B/O │  │- Operator Alert Dispatched    │
└──────────────────┘  └──────────────────┘ └──────────────────┘  └───────────────────────────────┘
```

---

## 4. Anti-Flapping Hysteresis Logic

To avoid rapid oscillating (flapping) between modes when metrics fluctuate around threshold boundaries:

1. **Separate Trigger & Recovery Thresholds**:
   - **Compute**: Triggered at $\text{CPU} \ge 85\%$; recovered only when $\text{CPU} < 70\%$.
   - **Network**: Triggered at $\text{Latency} \ge 500\text{ ms}$; recovered only when $\text{Latency} < 150\text{ ms}$.
   - **Disk**: Triggered at $\text{Free} < 500\text{ MB}$; recovered only when $\text{Free} > 1000\text{ MB}$.
2. **Consecutive Cycle Requirement**: Requires 3 consecutive violating observation cycles before entering a throttled state.
3. **Cooldown Timer**: Enforces a minimum 10.0-second cooldown window after any mode transition before allowing a recovery transition.

---

## 5. Critical Event Preservation Guarantee

> [!IMPORTANT]
> **Zero Silent Event Loss**: Under `EMERGENCY_DISK_PRESSURE`, non-critical diagnostic logs and raw debug traces may be purged, but **critical security events (VIP detections, watchlist matches, alerts, and access violations) are NEVER discarded**. All critical events are guaranteed retention in the local cryptographic ledger.
