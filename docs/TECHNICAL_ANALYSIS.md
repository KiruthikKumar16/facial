# Facial Recognition System - Comprehensive Technical Analysis

**Repository:** https://github.com/KiruthikKumar16/facial/tree/fix/runtime-data-sharing  
**Branch:** `fix/runtime-data-sharing`  
**Analysis Date:** 2026-09-01

---

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Current Data Flow](#current-data-flow)
3. [Key Components & Files](#key-components--files)
4. [Runtime Data Sharing Implementation](#runtime-data-sharing-implementation)
5. [Local Event Persistence](#local-event-persistence)
6. [Event Transmission to Backend](#event-transmission-to-backend)
7. [Retry & Error Handling](#retry--error-handling)
8. [Duplicate Handling](#duplicate-handling)
9. [Frontend-Backend Communication](#frontend-backend-communication)
10. [Current Limitations](#current-limitations)
11. [Potential Breaking Changes](#potential-breaking-changes)
12. [Recommended Files for Future Improvements](#recommended-files-for-future-improvements)

---

## System Architecture

### High-Level Overview
The system is a **distributed Edge-to-Cloud facial recognition platform** with three tightly integrated components:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│  EDGE NODE (Local)                  BACKEND (Cloud)        FRONTEND      │
│  ┌──────────────────┐              ┌──────────────┐      ┌──────────┐   │
│  │ Webcam/RTSP      │              │   FastAPI    │      │ Next.js  │   │
│  │    ↓             │              │   Uvicorn    │      │ React    │   │
│  │ InsightFace      │─── HTTPS ───▶│ PostgreSQL   │◀──── │ Dashboard│   │
│  │ (ONNX)           │  + REST API  │ (pgvector)   │      │          │   │
│  │    ↓             │              │              │  WS   └──────────┘   │
│  │ CSV Local Log    │              │ WebSocket    │◀────────────────┐    │
│  │ + DB Insert      │              │ Pub/Sub      │                 │    │
│  │    ↓             │              │              │                 │    │
│  │ pending/ (NPZ)   │              │ MJPEG Stream │──────────────────┘   │
│  │                  │              │              │                      │
│  └──────────────────┘              └──────────────┘                      │
│                                                                           │
│  ┌─ Known Faces ──┐                                                      │
│  │ gallery.npz    │                                                      │
│  │ (embeddings)   │◀────── Synced every 5 minutes                        │
│  └────────────────┘                                                      │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Edge** | Python 3.11, OpenCV, InsightFace, ONNX Runtime | Real-time face detection & embedding |
| **Backend** | FastAPI, SQLAlchemy, Python 3.11, Uvicorn | REST API, WebSocket hub, vector queries |
| **Database** | PostgreSQL (Supabase) + pgvector | Relational + vector storage |
| **Frontend** | Next.js 14, React 18, @tanstack/react-query, TailwindCSS | Real-time dashboard |
| **Deployment** | Render (Backend), Vercel (Frontend), Supabase (Database) | Cloud infrastructure |

---

## Current Data Flow

### End-to-End Detection Flow

```
1. EDGE CAPTURE
   ↓
   Webcam/RTSP Frame
   ↓
   CameraCapture.capture_frame() (OpenCV)
   ↓
   CameraPipeline.process_frame()
      - Resize frame for inference
      - InsightFaceDetector.detect() → face BBox
      - InsightFaceDetector.extract_embedding() → 512-dim tensor
   ↓
2. RECOGNITION
   ↓
   Recognizer.recognize(embedding) → (identity, confidence)
      - Load cosine similarity against known_faces/gallery.npz
      - If unknown → PendingSaver.save(embedding, crop)
   ↓
3. LOCAL LOGGING
   ↓
   DetectionLogger.log_detection()
      - Write synchronously to detections-YYYY-MM-DD.csv
      - Queue to background worker for async DB insert
   ↓
4. EDGE-TO-CLOUD TRANSMISSION
   ↓
   DetectionLogger._worker_loop()
      - Drains queue (thread-safe)
      - POST JSON to /api/detections with X-API-Key header
      - Retry logic with exponential backoff
   ↓
5. BACKEND INGESTION
   ↓
   @app.post("/api/detections")
      - Verify EDGE_API_KEY
      - Create/update Camera record
      - Resolve identity (lookup or create Profile)
      - Compute camera transitions if recognized
      - Create Detection record in PostgreSQL
      - Create Alert record if needed
      - Broadcast to WebSocket clients (alerts, kpis channels)
   ↓
6. BROADCAST TO FRONTEND
   ↓
   WebSocketConnectionManager.broadcast("alerts", face_log)
      - Send JSON message to all subscribed clients
   ↓
7. FRONTEND REACTION
   ↓
   connectAlertsWebSocket() → invalidateQueries(['alerts', 'face-logs'])
      - React Query refetches /api/logs
      - Dashboard re-renders with new detection
```

---

## Key Components & Files

### Edge Node (facial_recognition/)

| File | Responsibility |
|------|-----------------|
| **main.py** | Entry point; defines `CameraPipeline` class that orchestrates capture → detect → recognize → log |
| **main_cpu.py** | CPU-optimized variant with frame skipping & thread pooling |
| **capture.py** | `CameraCapture` class; manages OpenCV VideoCapture with reconnection logic |
| **detector.py** | `InsightFaceDetector` class; wraps InsightFace (buffalo_s) + ONNX Runtime with session options |
| **recognizer.py** | `Recognizer` class; loads gallery.npz embeddings; performs cosine similarity search; syncs from /api/internal/gallery every 5 min |
| **logger.py** | `DetectionLogger` class; CSV writing + async PostgreSQL insertion via background thread |
| **pending.py** | `PendingSaver` class; saves unknown face crops & embeddings to pending/*.npz with deduplication (60% cosine similarity threshold) |
| **edge_stream.py** | `EdgeFramePublisher` class; uploads annotated JPEG frames to backend via HTTPS POST or legacy WebSocket |
| **enroll.py** | CLI to enroll known faces into gallery.npz from known_faces/ directory |
| **review_pending.py** | GUI to review pending/*.npz, name faces, and move to known_faces/ |
| **config.yaml** | Camera sources, inference sizes, thresholds, camera routes, gallery path |

### Backend (backend/)

| File | Responsibility |
|------|-----------------|
| **main.py** | FastAPI application; defines all API routes and lifespan handlers |
| **database.py** | SQLAlchemy engine setup, pgvector extension loader, session factory |
| **models.py** | SQLAlchemy ORM models: Camera, Profile, Detection, Alert, Embedding, CameraTransition |
| **schemas.py** | Pydantic request/response models for API validation |
| **websocket.py** | `WebSocketConnectionManager` class; manages pub/sub channels (alerts, cameras, kpis) |
| **config.py** | Environment loading; settings parsing (DATABASE_URL, CORS_ORIGINS, ENABLE_FORENSIC_SEARCH, etc.) |
| **supabase_init.sql** | SQL to create pgvector extension and initialize schema |

### Frontend (facial-recognition-dashboard/)

| File | Responsibility |
|------|-----------------|
| **lib/api.ts** | Fetch functions + adapter layer to normalize backend responses |
| **lib/types.ts** | TypeScript interfaces mirroring backend schemas |
| **components/dashboard/dashboard.tsx** | Main Dashboard component; sets up WebSocket connections; coordinates tab switching |
| **components/dashboard/tabs/** | Individual tab implementations (Alerts, Forensic, Profiles, Analytics, System) |
| **components/providers.tsx** | React Query setup; ErrorBoundary wrapper |
| **app/page.tsx** | Entry point; renders Dashboard |

---

## Runtime Data Sharing Implementation

### How Data Flows Between Edge & Backend at Runtime

#### 1. **Dual-Write Pattern** (Synchronous CSV + Asynchronous DB)

**Location:** `facial_recognition/logger.py:DetectionLogger.log_detection()`

```python
# SYNCHRONOUS: Write to CSV immediately
self.current_writer.writerow({
    'timestamp': now.isoformat(),
    'camera_id': camera_id,
    'bbox': '[x1, y1, x2, y2]',
    'identity': identity,
    'confidence': confidence,
})
self.current_file.flush()

# ASYNCHRONOUS: Queue for background DB thread
self.log_queue.put((camera_id, identity, confidence, bbox, now, age, gender))
```

**Rationale:**  
- CSV write is synchronous to prevent FPS drop (critical for real-time).
- DB insert is async (background thread) to avoid blocking the camera loop.
- If the backend is unreachable, CSV remains as fallback transaction log.

#### 2. **Background Worker Thread** (Retry Loop)

**Location:** `facial_recognition/logger.py:DetectionLogger._worker_loop()`

```python
while not self._stop_event.is_set():
    items = []
    # Drain queue
    while True:
        try:
            item = self.log_queue.get_nowait()
            items.append(item)
            self.log_queue.task_done()
        except queue.Empty:
            break
    
    items = retry_queue + items  # Retry failed items
    retry_queue = []
    
    if not items:
        time.sleep(1.0)
        continue
    
    for item in items:
        # Build JSON payload
        payload = {
            "camera_id": camera_id,
            "identity": identity,
            "confidence": float(confidence),
            "bbox": [int(x) for x in bbox],
            "timestamp": now.isoformat(),
            "age": int(age),
            "gender": str(gender),
        }
        
        try:
            # POST to backend with API key
            req = urllib.request.Request(
                f"{API_URL}/api/detections",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=2.0) as f:
                pass
        except Exception as e:
            # Move to retry queue
            retry_queue.append(item)
    
    if retry_queue:
        time.sleep(2.0)  # Backoff before next batch
```

**Key Design:**
- Queue-based producer-consumer pattern prevents blocking.
- Failed items retry in subsequent iterations.
- Backoff strategy (2s retry delay) prevents thundering herd.
- No persistent queue across restarts (in-memory queue).

#### 3. **Gallery Synchronization** (5-Minute Polling)

**Location:** `facial_recognition/recognizer.py:Recognizer._load_gallery()` & `_fetch_gallery_from_api()`

```python
def _load_gallery(self, gallery_path: str) -> None:
    def sync():
        while True:
            time.sleep(300)  # 5 minutes
            self._fetch_gallery_from_api(gallery_path)
    
    success = self._fetch_gallery_from_api(gallery_path)
    if not success:
        self._load_from_file(gallery_path)  # Fallback
    
    t = threading.Thread(target=sync, daemon=True)
    t.start()
```

**Protocol:**
- Edge calls GET `/api/internal/gallery` (requires EDGE_API_KEY).
- Backend returns `{"labels": [names...], "embeddings": [[512-dim floats]...]}`.
- If API succeeds, gallery updates in-memory; if fails, falls back to local file.
- 5-minute cadence balances freshness vs. network load.

#### 4. **Frame Publishing** (MJPEG via HTTPS or Legacy WebSocket)

**Location:** `facial_recognition/edge_stream.py:EdgeFramePublisher._run()`

**Modern (HTTPS POST):**
```python
# Upload latest annotated JPEG frame
response = session.post(
    f"{API_URL}/api/internal/cameras/{camera_id}/frame",
    data=encoded_jpeg,
    headers={"Content-Type": "image/jpeg", "X-API-Key": api_key},
    timeout=10,
)
```

**Legacy (WebSocket):**
```python
# WebSocket at wss://backend/ws/video/push/{camera_id}?api_key={key}
websocket.send_bytes(jpeg_bytes)
```

**Backend Reception:**
- POST handler stores JPEG in `_frame_store` dictionary.
- MJPEG consumers poll `_frame_store` for latest frame + notify via `asyncio.Event`.

---

## Local Event Persistence

### CSV Logging

**Location:** `facial_recognition/logger.py:DetectionLogger._open_for_date()`

**File Pattern:** `detections-YYYY-MM-DD.csv`

**Structure:**
```csv
timestamp,camera_id,bbox,identity,confidence
2026-08-31T14:23:45Z,webcam,"[100, 200, 300, 400]",John Smith,0.9234
2026-08-31T14:23:47Z,webcam,"[102, 198, 298, 402]",Unknown,0.4100
```

**Behavior:**
- One file per calendar day.
- Synchronous writes (flushed immediately).
- No header rewrite if file exists.
- Used as fallback if backend is unreachable.

### Pending Face Cache

**Location:** `facial_recognition/pending.py:PendingSaver`

**File Pattern:** `pending_Person_N_TIMESTAMP.npz`

**Contents (NumPy .npz format):**
```
- embedding: (512,) float32 array
- face_image: (H, W, 3) uint8 BGR image
- label: "Person 1" (string)
- timestamp: integer milliseconds
```

**Deduplication Logic:**
- When saving unknown face: compute cosine similarity against existing pending embeddings.
- If similarity ≥ 0.60 (60%), return existing label ("Person 1").
- Else: assign new label ("Person 2").

**Purpose:**
- Allows offline review via `python review_pending.py`.
- When enrolled, moves to `known_faces/{name}/` and updates gallery.npz.

---

## Event Transmission to Backend

### API Endpoint: POST /api/detections

**Authentication:** X-API-Key header (EDGE_API_KEY)

**Request Body (JSON):**
```json
{
  "camera_id": "webcam",
  "identity": "John Smith",
  "confidence": 0.9234,
  "bbox": [100, 200, 300, 400],
  "timestamp": "2026-08-31T14:23:45.123456Z",
  "age": 35,
  "gender": "male"
}
```

**Backend Processing:**

```python
@app.post("/api/detections", response_model=DetectionResponse)
async def create_detection(
    req: DetectionCreateRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_edge_node)
):
    # 1. Ensure camera exists
    camera = db.query(Camera).filter(Camera.id == req.camera_id).first()
    if not camera:
        camera = Camera(id=req.camera_id, name=req.camera_id, status=CameraStatusEnum.online)
        db.add(camera)
        db.commit()
    
    # 2. Resolve identity
    profile, profile_id, status = resolve_detection_identity(db, req.identity)
    
    # 3. Check for camera transitions (if recognized)
    if profile_id:
        previous = db.query(Detection).filter(
            Detection.profile_id == profile_id,
            Detection.timestamp < req.timestamp,
        ).order_by(Detection.timestamp.desc()).first()
        
        if previous and previous.camera_id != req.camera_id:
            travel_seconds = (req.timestamp - previous.timestamp).total_seconds()
            if 0 < travel_seconds <= max_camera_travel_seconds:
                db.add(CameraTransition(...))  # Record movement
    
    # 4. Create Detection record
    detection = Detection(
        id=str(uuid.uuid4()),
        camera_id=req.camera_id,
        profile_id=profile_id,
        timestamp=req.timestamp,
        status=status,
        confidence=req.confidence,
        bbox=f"[{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]",
        age=req.age,
        gender=parse_gender(req.gender),
    )
    db.add(detection)
    db.commit()
    
    # 5. Create Alert if needed
    should_alert, severity, reason = alert_meta_for_detection(status, profile, req.identity)
    if should_alert:
        alert = Alert(
            id=str(uuid.uuid4()),
            detection_id=detection.id,
            camera_id=req.camera_id,
            profile_id=profile_id,
            timestamp=req.timestamp,
            severity=severity,
            reason=reason,
        )
        db.add(alert)
        db.commit()
    
    # 6. Broadcast to WebSocket clients
    face_log = build_face_log_payload(detection, camera, profile)
    asyncio.create_task(manager.broadcast("alerts", face_log))
    asyncio.create_task(manager.broadcast("kpis", {"refresh": True}))
    
    return DetectionResponse.from_orm(detection)
```

**Identity Resolution Logic:**

```python
def resolve_detection_identity(db: Session, identity: str):
    # Check if identity is pending unknown ("Unknown", "Person N")
    if is_pending_unknown_identity(identity):
        return None, None, DetectionStatusEnum.unknown
    
    # Lookup existing profile by name
    profile = db.query(Profile).filter(Profile.name == identity).first()
    if profile:
        status = DetectionStatusEnum.flagged if profile.role in ('blacklist', 'watchlist') else DetectionStatusEnum.recognized
        return profile, profile.id, status
    
    # Create new profile on-the-fly
    new_id = str(uuid.uuid4())
    profile = Profile(id=new_id, name=identity, role=ProfileRoleEnum.visitor)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile, new_id, DetectionStatusEnum.recognized
```

**Alert Decision Tree:**

```
if status == unknown:
    → Medium alert: "Unknown face detected"
elif profile.role == blacklist:
    → Critical alert: "Blacklist match"
elif profile.role == watchlist:
    → High alert: "Watchlist match"
elif status == flagged:
    → High alert: "Flagged identity"
else:
    → No alert (recognized, trusted person)
```

---

## Retry & Error Handling

### Edge → Backend Retry Logic

**Location:** `facial_recognition/logger.py:DetectionLogger._worker_loop()`

**Mechanism:**
1. **Queue Drain:** Fetch all pending items from the thread-safe queue.
2. **Retry Integration:** Prepend failed items from previous iteration.
3. **POST Attempt:** Try each item with 2-second timeout.
4. **Failure Handling:** On exception, append to retry_queue.
5. **Backoff:** If retry_queue has items, sleep 2 seconds before next iteration.

**Pseudocode:**
```
retry_queue = []
while not stopped:
    items = drain_queue() + retry_queue
    retry_queue = []
    
    for item in items:
        try:
            POST /api/detections
            success = True
        except Exception as e:
            retry_queue.append(item)
            success = False
    
    if retry_queue:
        sleep(2.0)  # Exponential backoff cap at 30s (not implemented)
    else:
        sleep(1.0)
```

**No Built-In Circuit Breaker:**
- System continues retrying indefinitely if backend is down.
- Items accumulate in memory queue (Python list).
- On edge node restart, in-memory queue is lost (only CSV persists).

### Backend → Database Error Handling

**Location:** `backend/main.py:create_detection()`

**Failure Scenarios:**
1. **Database Connection Error:** SQLAlchemy raises exception; FastAPI returns 500.
2. **Missing Camera:** Auto-create Camera record.
3. **Invalid Profile Name:** Auto-create Profile record as "visitor" role.

**No Explicit Retry:**
- Edge node is responsible for retrying failed requests.
- Backend does not queue failed detections for later retry.

### WebSocket Broadcast Failure Handling

**Location:** `backend/websocket.py:WebSocketConnectionManager.broadcast()`

```python
async def broadcast(self, channel: str, message: Dict[str, Any]):
    payload = json.dumps({"type": channel, "timestamp": datetime.utcnow().isoformat(), "data": message})
    
    disconnected = []
    for connection in self.active_connections[channel]:
        try:
            await connection.send_text(payload)
        except Exception as e:
            logger.warning(f"Failed to send to {channel}: {e}")
            disconnected.append(connection)
    
    # Clean up dead connections
    for conn in disconnected:
        await self.disconnect(channel, conn)
```

**Behavior:**
- If a client WebSocket is dead, it's silently removed from the broadcast list.
- Other subscribers still receive the message.
- No persistent queue for missed messages.

---

## Duplicate Handling

### Edge-Side Deduplication (PendingSaver)

**Location:** `facial_recognition/pending.py:PendingSaver._find_matching_label()`

**Threshold:** 0.60 (60% cosine similarity)

```python
def _find_matching_label(self, emb: np.ndarray) -> Optional[str]:
    if not self._known_unknowns:
        return None
    
    emb_norm = np.linalg.norm(emb) + 1e-10
    for existing, label in zip(self._known_unknowns, self._unknown_labels):
        sim = float(np.dot(existing, emb) / (np.linalg.norm(existing) * emb_norm))
        if sim >= self.DUPLICATE_THRESHOLD:  # 0.60
            return label
    return None
```

**Usage:** When an unknown face is detected, check if it matches an existing pending face. If yes, reuse the same "Person N" label; if no, create new.

### Backend-Side Deduplication (Vector Self-Join)

**Location:** `backend/main.py:get_duplicates()`

**Query Logic (not shown in truncated main.py, but referenced in FINAL_REPORT.md):**

```sql
SELECT
    e1.profile_id AS profileAId,
    e2.profile_id AS profileBId,
    (1 - (e1.vector <=> e2.vector)) AS cosineSimilarity
FROM embeddings e1
JOIN embeddings e2 ON e1.profile_id < e2.profile_id
WHERE (1 - (e1.vector <=> e2.vector)) > 0.90  -- 90% similar
ORDER BY cosineSimilarity DESC;
```

**Manual Merge Endpoint:**

```python
@app.post("/api/profiles/merge")
def merge_profiles(req: ProfileMergeRequest, db: Session = Depends(get_db)):
    keep_id = req.keepProfile or req.keepProfileId or req.profileAId
    delete_id = req.profileBId if keep_id == req.profileAId else req.profileAId
    
    # Transactional re-parenting
    db.query(Detection).filter(Detection.profile_id == delete_id).update({"profile_id": keep_id})
    db.query(Embedding).filter(Embedding.profile_id == delete_id).update({"profile_id": keep_id})
    db.query(Alert).filter(Alert.profile_id == delete_id).update({"profile_id": keep_id})
    
    keep_profile.embedding_count += delete_profile.embedding_count
    db.delete(delete_profile)
    db.commit()
    
    return {"merged": True, "keptProfileId": keep_id, "deletedProfileId": delete_id}
```

**No Automatic Merging:**
- Duplicates are **detected** and presented to operator via dashboard.
- Merge is **manual** (one-click confirmation in UI).
- Merge is **transactional** (atomicity guaranteed).

### Detection-Level Deduplication (60-Second Window)

**Location:** `facial_recognition/logger.py:DetectionLogger.log_detection()`

```python
# Suppress duplicate records (same camera_id, identity) within a short window
key = (camera_id, identity)

with self.lock:
    self._purge_dedup(now_ts)  # Clean old entries
    
    last = self._dedup.get(key)
    if last is not None and (now_ts - last) < self._dedup_window:  # 60 seconds default
        # Duplicate within window; skip logging
        return
    
    self._dedup[key] = now_ts
    # Proceed to CSV + queue...
```

**Purpose:** Prevent same person moving slightly within frame from triggering multiple logs in rapid succession.

---

## Frontend-Backend Communication

### WebSocket Channels

**Connection Setup (dashboard.tsx):**

```typescript
useEffect(() => {
  const wsAlerts = connectAlertsWebSocket((data) => {
    // Handle alert data
    const newLog = adaptFaceLog(data)
    queryClient.setQueryData(['face-logs'], (oldData) => [newLog, ...oldData].slice(0, 100))
    queryClient.invalidateQueries({ queryKey: ['alerts'] })
  })
  
  const wsCameras = connectCamerasWebSocket((data) => {
    queryClient.invalidateQueries({ queryKey: ['cameras'] })
  })
  
  const wsKpis = connectKpisWebSocket((data) => {
    queryClient.invalidateQueries({ queryKey: ['kpis'] })
  })
  
  return () => {
    wsAlerts.close()
    wsCameras.close()
    wsKpis.close()
  }
}, [queryClient])
```

**Three Channels:**

| Channel | Trigger | Payload | Consumer |
|---------|---------|---------|----------|
| `/ws/alerts` | `POST /api/detections` → broadcast() | Full `FaceLog` object | AlertsTab, FaceLog list |
| `/ws/cameras` | Camera health updates (not auto-triggered) | `{"refresh": True}` | System tab camera list |
| `/ws/kpis` | Detection or alert creation | `{"refresh": True}` | System tab KPI cards |

**WebSocket Reception (lib/api.ts):**

```typescript
export const connectAlertsWebSocket = (onMessage: (data: any) => void): WebSocket => {
  const ws = new WebSocket(wsUrl('alerts'))
  ws.onmessage = (event) => {
    try {
      const { data } = JSON.parse(event.data)
      onMessage(data)
    } catch (e) {
      console.error('WebSocket parse error', e)
    }
  }
  ws.onerror = () => console.warn(`WebSocket unavailable: ${wsUrl('alerts')}`)
  return ws
}
```

### React Query Integration

**Query Invalidation Pattern:**

```typescript
// When WebSocket message arrives:
queryClient.invalidateQueries({ queryKey: ['face-logs'] })

// React Query auto-calls fetchFaceLogs():
export const fetchFaceLogs = async (limit: number = 100, offset: number = 0): Promise<FaceLog[]> => {
  const response = await fetch(apiUrl(`/api/logs?limit=${limit}&offset=${offset}`))
  return response.json()
}
```

**Stale Time & Refetch Strategy:**
- Default stale time: 30 seconds.
- On WebSocket message: invalidate immediately (triggers refetch).
- Refetch on window focus: disabled.

### API Polling Endpoints (Rest)

**Alerts Tab:**
- `GET /api/alerts?limit=50` (periodic refetch or manual)
- `POST /api/alerts/{alert_id}/acknowledge` (manual interaction)

**Forensic Tab:**
- `POST /api/forensic/search` (file upload, blocking)
- Returns: list of `ForensicMatch` objects

**Profiles Tab:**
- `GET /api/profiles` (periodic refetch)
- `POST /api/profiles` (file upload with photos)
- `POST /api/profiles/merge` (manual merge request)
- `GET /api/analytics/duplicates` (periodic refetch)

**Analytics Tab:**
- `GET /api/analytics/footfall?days=7` (periodic)
- `GET /api/analytics/movement-network?hours=24` (periodic)
- `GET /api/analytics/trajectory?profileId={id}&hours=24` (on-demand)
- `GET /api/analytics/age-distribution` (periodic)
- `GET /api/analytics/gender-distribution` (periodic)
- `GET /api/analytics/attendance?days=7` (periodic)

**System Tab:**
- `GET /api/kpis` (periodic, also via WebSocket invalidation)
- `GET /api/cameras` (periodic, also via WebSocket invalidation)
- `GET /api/thresholds` (periodic)
- `POST /api/thresholds` (manual update)

---

## Current Limitations

### 1. **No Persistent Message Queue**
- In-memory queue is lost on edge node restart.
- Only CSV remains as fallback.
- No guaranteed delivery for PostgreSQL inserts if network is unreliable.
- **Implication:** Between restart and backend reconnection, events may not reach database.

### 2. **No Circuit Breaker**
- Edge node retries infinitely if backend is down.
- No adaptive backoff (retry delay capped at 2s, not exponential).
- Potential for resource exhaustion under sustained backend outage.
- **Implication:** If Render backend is down for 1 hour, 1800 retry attempts occur (one per 2s).

### 3. **Gallery Sync Latency (5-Minute Polling)**
- New profiles enrolled on backend take up to 5 minutes to reach edge node.
- No push notification for profile changes.
- **Implication:** If a new employee is enrolled at 9:00 AM, they won't be recognized until 9:05 AM.

### 4. **No Deduplication Across Camera Transitions**
- Each camera processes frames independently.
- If same person walks from camera A to camera B within 60 seconds, **both detections are logged**.
- Only gallery Recognizer tries to match against known faces; if unknown on both cameras, creates duplicate unknown entry.
- **Implication:** Footfall analytics double-count the same individual across cameras.

### 5. **Manual Duplicate Merging**
- Backend detects duplicates but requires manual operator click to merge.
- No API endpoint for automatic batch merge.
- **Implication:** Dashboard accumulates stale profiles over time without active curation.

### 6. **No Image Caching or Snapshot Storage**
- Frames are not persisted; only metadata (bbox, confidence, age, gender) is stored.
- Cannot retrieve the original face crop later for forensic review.
- **Implication:** If operator needs to re-examine a detection, no photo is available.

### 7. **WebSocket No Offline Queue**
- If frontend is disconnected, missed WebSocket messages are dropped.
- Frontend must refetch from REST API to recover.
- **Implication:** If dashboard tab is backgrounded during a flurry of detections, some events are not shown until manual refetch.

### 8. **No End-to-End Encryption**
- API calls use plain HTTP (local dev) or HTTPS (Render, Vercel).
- WebSockets use ws:// (local dev) or wss:// (cloud).
- No additional payload encryption between edge and backend.
- **Implication:** Network MITM could intercept face embeddings or identity names.

### 9. **No Rate Limiting**
- Backend /api/detections accepts unlimited requests from edge node (only API key required).
- No per-camera quota or throttling.
- **Implication:** Misconfigured edge node could flood backend and cause DoS.

### 10. **No Audit Logging for Sensitive Operations**
- Profile merges, threshold changes, and acknowledgements are not logged to audit trail.
- Only PostgreSQL transaction logs (if enabled) record changes.
- **Implication:** No forensic trail for compliance or incident investigation.

---

## Potential Breaking Changes

### 1. **Changing CSV Format**
- If `detections-YYYY-MM-DD.csv` schema changes (e.g., add column), old files become incompatible.
- **Risk:** High (any tool parsing CSV will break).
- **Recommendation:** Version the CSV format or add migration utility.

### 2. **Changing API Request/Response Schema**
- If `/api/detections` request body adds required field, old edge nodes will fail.
- If response schema changes, frontend adapters may fail to normalize.
- **Risk:** High (backward compatibility breaks).
- **Recommendation:** Use semantic versioning; provide deprecation period.

### 3. **Changing Gallery Sync Format**
- If `/api/internal/gallery` response changes (e.g., embeddings become bytes instead of lists), Recognizer.py will fail to load.
- **Risk:** Medium (affects only dynamic gallery fetch, fallback is local file).
- **Recommendation:** Include version field in response; support multiple formats.

### 4. **Renaming or Removing Profiles**
- If a Profile.id is deleted manually, all Detection and Alert foreign keys become orphaned.
- PostgreSQL allows orphaning if CASCADE is not set on relationships.
- **Risk:** Low (ORM cascade is set, but manual SQL could break it).
- **Recommendation:** Always use ORM for profile deletion.

### 5. **Changing Detection Status or Profile Role Enums**
- If DetectionStatus.unknown is renamed, filter queries break.
- If ProfileRole.blacklist is removed, alert decision tree breaks.
- **Risk:** High (enum values hardcoded throughout codebase).
- **Recommendation:** Maintain backward compatibility; add migration for existing data.

### 6. **Changing WebSocket Channel Names**
- Frontend hardcodes `connectAlertsWebSocket()` which uses `/ws/alerts` channel.
- If backend renames to `/ws/detections`, frontend must update.
- **Risk:** High (both sides must change simultaneously).
- **Recommendation:** Document channel contract; coordinate releases.

### 7. **Changing Database Connections Pool Strategy**
- Currently uses `NullPool` (no connection pooling).
- Switching to `QueuePool` could break if thread count assumptions are wrong.
- **Risk:** Medium (affects connection exhaustion behavior).
- **Recommendation:** Test connection pool under load before switching.

### 8. **Changing pgvector Extension Availability**
- Code assumes pgvector is available (`Vector(512)` column type).
- If deployed to non-Supabase PostgreSQL without pgvector, schema creation fails.
- **Risk:** Low (deployment guide enforces Supabase).
- **Recommendation:** Add graceful fallback or validation in startup.

---

## Recommended Files to Modify for Future Improvements

### 1. **Enable Persistent Queue (Prevent Data Loss)**
- **Files:** `facial_recognition/logger.py`
- **Changes:**
  - Replace in-memory `queue.Queue` with SQLite-backed queue.
  - Serialize/deserialize items to SQLite rows.
  - On startup, replay unACKed rows from SQLite before processing new items.
  - Mark items as ACKed only after successful POST.
- **Alternative:** Use Redis if infrastructure allows.

### 2. **Add Circuit Breaker Pattern**
- **Files:** `facial_recognition/logger.py`
- **Changes:**
  - Implement exponential backoff: retry_delay = min(2^attempt, 300) seconds.
  - Track failure count per camera_id.
  - After N consecutive failures (e.g., 10), switch to "degraded" mode (log to CSV only, reduce retry frequency).
  - Add recovery probe: every 5 minutes, try a single POST to check if backend is back.
- **Benefit:** Reduce log spam and CPU usage during prolonged outages.

### 3. **Push-Based Gallery Sync (Real-Time Profile Updates)**
- **Files:** `facial_recognition/recognizer.py`, `backend/main.py`
- **Changes:**
  - Add new endpoint: `POST /api/internal/gallery` for edge to subscribe to gallery changes via WebSocket or Server-Sent Events.
  - On POST /api/profiles or /api/profiles/merge, notify all connected edge nodes immediately.
  - Edge node updates Recognizer.labels and Recognizer.embeddings in real-time.
- **Benefit:** New profiles recognized immediately; no 5-minute lag.

### 4. **Cross-Camera Deduplication (Global Tracking)**
- **Files:** `backend/main.py` (expand create_detection), `backend/models.py` (add TrackingSession or IdentityTrack model)
- **Changes:**
  - Extend camera transition logic to detect same identity across all cameras in a single session.
  - Add temporal window: if same profile_id seen within 30 seconds across different cameras, link as single "visit" or "track".
  - Create compound Alert on inter-camera transition for watchlist/blacklist.
- **Benefit:** Accurate footfall; prevent double-counting.

### 5. **Snapshot Storage (Face Crop Persistence)**
- **Files:** `backend/main.py` (create_detection), `backend/models.py` (add Snapshot model)
- **Changes:**
  - Extract face crop from request (use bbox to crop from uploaded JPEG or edge node frame).
  - Store cropped image to Supabase Storage or S3.
  - Link Snapshot FK to Detection.id.
  - Frontend fetches snapshot URL for display in alerts.
- **Benefit:** Forensic review; operator can verify false positives.

### 6. **Automatic Batch Duplicate Merging**
- **Files:** `backend/main.py`, `backend/models.py`
- **Changes:**
  - Add threshold-based auto-merge flag to Profile model (default: off).
  - Add scheduled task or cron job: every night, fetch duplicates with > 95% similarity, auto-merge if flag is enabled.
  - Log audit trail of auto-merges.
- **Benefit:** Reduce manual operator overhead.

### 7. **Audit Logging**
- **Files:** `backend/main.py`, `backend/models.py` (add AuditLog table)
- **Changes:**
  - Wrap sensitive endpoints: /api/profiles/merge, /api/alerts/{id}/acknowledge, /api/thresholds POST.
  - Before mutation, log: timestamp, user (if auth enabled), operation, old_value, new_value.
  - Expose read-only audit log endpoint: GET /api/audit-logs.
- **Benefit:** Compliance; incident investigation.

### 8. **Rate Limiting**
- **Files:** `backend/main.py` (add middleware)
- **Changes:**
  - Install `slowapi` or similar rate-limit library.
  - Apply limits:
    - POST /api/detections: 100 req/min per camera_id.
    - POST /api/forensic/search: 10 req/min per IP.
    - GET /api/logs: 30 req/min per session.
  - Return 429 Too Many Requests when exceeded.
- **Benefit:** DoS prevention; protect shared infrastructure.

### 9. **Structured Logging & Observability**
- **Files:** `facial_recognition/logger.py`, `backend/main.py`, `backend/websocket.py`
- **Changes:**
  - Replace print() statements and logger.info() with structured JSON logging (e.g., `python-json-logger`).
  - Include trace IDs for request correlation.
  - Export logs to ELK or Cloud Logging for centralized analysis.
  - Add Prometheus metrics: detection latency, queue depth, API error rate.
- **Benefit:** Easier debugging and SLO monitoring.

### 10. **Graceful Shutdown & Health Checks**
- **Files:** `backend/main.py` (enhance lifespan), `facial_recognition/main.py`
- **Changes:**
  - Add endpoint: GET /health/live (is server running?) and GET /health/ready (is DB connected?).
  - On SIGTERM, set flag to reject new requests but finish in-flight requests within 30s timeout.
  - Notify edge nodes of planned downtime via /api/internal/health endpoint.
- **Benefit:** Kubernetes-friendly; zero-downtime deployments.

---

## Summary Table: Critical Data Flow Points

| **Flow Stage** | **File(s)** | **Sync/Async** | **Persistence** | **Retries** | **Broadcast** |
|---|---|---|---|---|---|
| Frame Capture | capture.py | Sync | Memory buffer | N/A | No |
| Face Detection | detector.py | Sync | Memory | N/A | No |
| Embedding Extract | detector.py | Sync | Memory | N/A | No |
| Recognition | recognizer.py | Sync | Memory (loaded from gallery.npz) | N/A | No |
| CSV Log | logger.py | Sync | File system | N/A | No |
| Queue to DB | logger.py | Async (bg thread) | Memory queue | Yes (retry_queue) | No |
| HTTP POST | logger.py (_worker_loop) | Async | Retry queue | Yes (2s backoff) | No |
| Backend Ingest | main.py (create_detection) | Async (FastAPI) | PostgreSQL | N/A (edge retries) | Yes (/ws/alerts, /ws/kpis) |
| Alert Creation | main.py | Async | PostgreSQL | N/A | Yes (/ws/alerts) |
| WebSocket Broadcast | websocket.py | Async | Dropped if client disconnects | Client must refetch | Yes (to all subscribers) |
| Frontend Refetch | api.ts (fetchFaceLogs) | Async | React Query cache | Automatic retry on fail | React Query invalidation |
| Frontend Render | dashboard.tsx | Sync | Browser DOM | N/A | UI updates |

---

## Testing Coverage

**Current Status:** No automated tests found (no pytest, unittest, or test/ directory).

**Recommended Test Suite:**
1. **Unit:** detector.py, recognizer.py, logger.py, websocket.py (mocked HTTP/DB).
2. **Integration:** End-to-end flow from capture to dashboard update.
3. **Load:** 10 cameras × 5 FPS = 50 detections/sec over 1 hour.
4. **Failover:** Backend unavailable → verify CSV + retry queue behavior.

---

**END OF TECHNICAL ANALYSIS**
