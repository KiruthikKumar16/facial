# Facial Recognition Surveillance System - Implementation Guide

## 📋 Architecture Overview

```
┌──────────────────────────┐
│  React Dashboard (3000)  │
│  - Real-time KPIs        │
│  - Camera Status         │
│  - Alert Management      │
│  - Profile Gallery       │
└───────────┬──────────────┘
            │
            │ HTTP + WebSocket
            ↓
┌──────────────────────────────────┐
│  FastAPI Backend (8000)          │
│  - REST API Endpoints            │
│  - WebSocket Real-time Updates   │
│  - Database ORM (SQLAlchemy)     │
│  - Face Similarity Search        │
└────────────┬─────────────────────┘
             │
             ↓
┌──────────────────────────────────────┐
│  PostgreSQL + pgvector               │
│  - Detection Logs                    │
│  - Profile Gallery + Embeddings      │
│  - Camera Health                     │
│  - Alerts & Thresholds              │
└──────────────────────────────────────┘
             ↑
             │ CSV Import
             │
┌──────────────────────────────────────┐
│  Facial Recognition Core             │
│  - detector.py (InsightFace)        │
│  - recognizer.py (Gallery Matching)  │
│  - detections.csv (Detection Logs)   │
└──────────────────────────────────────┘
```

---

## 🗂️ Project Structure

```
facial/
├── facial_recognition/          # Core facial recognition engine
│   ├── detector.py              # Face detection with InsightFace
│   ├── recognizer.py            # Gallery matching
│   ├── capture.py               # Camera/stream capture
│   ├── enroll.py                # Gallery enrollment
│   ├── main.py                  # GPU pipeline
│   ├── main_cpu.py              # CPU-optimized pipeline
│   └── logger.py                # Detection logging to CSV
│
├── backend/                     # FastAPI backend (NEW)
│   ├── main.py                  # FastAPI app + endpoints
│   ├── models.py                # SQLAlchemy ORM models
│   ├── schemas.py               # Pydantic request/response models
│   ├── database.py              # PostgreSQL connection
│   ├── config.py                # Environment configuration
│   ├── websocket.py             # WebSocket connection manager
│   ├── routers/                 # Endpoint modules (extensible)
│   └── requirements.txt          # Python dependencies
│
├── facial-recognition-dashboard/ # Next.js Frontend (EXISTING)
│   ├── app/                     # Next.js app directory
│   ├── lib/
│   │   ├── api.ts              # API client (TO UPDATE)
│   │   ├── types.ts            # TypeScript models
│   │   └── mock-data.ts        # Mock data (REMOVE when live)
│   ├── components/             # React components
│   └── package.json            # Node.js dependencies
│
├── known_faces/                # Gallery directory
├── pending/                    # Unknown faces for review
├── detections.csv             # Raw detection logs
├── config.yaml                # System configuration
│
└── run-*.ps1                  # Launch scripts
```

---

## 🛠️ Setup Instructions

### 1️⃣ **PostgreSQL Installation** (Windows)

```powershell
# Download from https://www.postgresql.org/download/windows/
# OR use Chocolatey
choco install postgresql

# Create database
createdb facial_recognition

# Verify
psql -U postgres -d facial_recognition -c "SELECT version();"
```

### 2️⃣ **Backend Setup**

```powershell
cd backend
python -m venv venv          # Create virtual environment
.\venv\Scripts\Activate.ps1  # Activate
pip install -r requirements.txt
```

### 3️⃣ **Frontend Setup**

```powershell
cd facial-recognition-dashboard

# Install dependencies (use pnpm for speed, or npm)
pnpm install   # Recommended
# OR
npm install
```

---

## 🚀 Running the System

### **Option A: Two Terminal Windows (Recommended)**

**Terminal 1 - Backend:**
```powershell
.\run-backend.ps1
# Or manually:
cd backend && python main.py
```
Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Database initialized
```

**Terminal 2 - Frontend:**
```powershell
.\run-frontend.ps1
# Or manually:
cd facial-recognition-dashboard && pnpm dev
```
Expected output:
```
▲ Next.js 16.3.0
- Local:        http://localhost:3000
```

### **Option B: Quick Setup Script**
```powershell
.\setup-all.ps1   # Installs dependencies & shows launch commands
```

---

## 📡 API Endpoints

### **Health Check**
```http
GET http://localhost:8000/health
```

### **System KPIs**
```http
GET /api/kpis
Response: {
  "total_detections": 4866,
  "unique_individuals": 12,
  "total_profiles": 25,
  "cameras_online": 3,
  "critical_alerts": 2,
  "recognitions_today": 341,
  "unknowns_today": 15,
  "average_confidence": 0.92
}
```

### **Cameras**
```http
GET /api/cameras
Response: [{
  "id": "webcam",
  "name": "Main Lobby",
  "status": "online",
  "fps": 24,
  "gpu_load": 62.0,
  "detections_today": 1284
}]
```

### **Detection Logs**
```http
GET /api/logs?limit=100&offset=0
Response: [{
  "id": "...",
  "camera_id": "webcam",
  "timestamp": "2026-08-14T12:34:56",
  "status": "recognized",
  "confidence": 0.95,
  "profile_name": "Kiru",
  "age": 28,
  "gender": "male"
}]
```

### **Alerts**
```http
GET /api/alerts?limit=50
Response: [{
  "id": "...",
  "severity": "high",
  "reason": "Blacklist match detected",
  "timestamp": "2026-08-14T12:34:56",
  "acknowledged": false
}]
```

### **Profiles (Gallery)**
```http
GET /api/profiles
Response: [{
  "id": "profile-1",
  "name": "Kiru",
  "role": "employee",
  "embedding_count": 12,
  "last_seen": "2026-08-14T12:30:00"
}]
```

### **Model Thresholds**
```http
GET /api/thresholds
Response: {
  "similarity_confidence": 0.60,
  "liveness_threshold": 0.50,
  "age_variance": 5.0
}

POST /api/thresholds
Body: {
  "similarity_confidence": 0.65,
  "liveness_threshold": 0.55,
  "age_variance": 3.0
}
```

---

## 🔌 WebSocket Channels

Connect to real-time updates:

```typescript
// Alerts channel
const ws = new WebSocket('ws://localhost:8000/ws/alerts');
ws.onmessage = (event) => {
  const { type, timestamp, data } = JSON.parse(event.data);
  // { type: "alerts", timestamp: "2026-08-14T...", data: {...} }
};

// Cameras channel
const ws = new WebSocket('ws://localhost:8000/ws/cameras');
ws.onmessage = (event) => {
  // Real-time camera health updates
};

// KPIs channel
const ws = new WebSocket('ws://localhost:8000/ws/kpis');
ws.onmessage = (event) => {
  // Real-time KPI updates
};
```

---

## 💾 Database Schema

### **Cameras Table**
```sql
CREATE TABLE cameras (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  zone VARCHAR,
  ip_address VARCHAR,
  status VARCHAR,  -- online, degraded, offline
  fps FLOAT,
  gpu_load FLOAT,
  cpu_load FLOAT,
  detections_today INTEGER,
  created_at TIMESTAMP
);
```

### **Profiles Table**
```sql
CREATE TABLE profiles (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  role VARCHAR,  -- employee, vip, visitor, blacklist, watchlist
  department VARCHAR,
  embedding_count INTEGER,
  enrolled_at TIMESTAMP,
  last_seen TIMESTAMP
);
```

### **Embeddings Table (pgvector)**
```sql
CREATE TABLE embeddings (
  id VARCHAR PRIMARY KEY,
  profile_id VARCHAR REFERENCES profiles(id),
  vector vector(512),  -- 512-dim face embedding
  created_at TIMESTAMP
);

-- Create index for similarity search
CREATE INDEX embeddings_idx ON embeddings USING ivfflat (vector vector_cosine_ops);
```

### **Detections Table**
```sql
CREATE TABLE detections (
  id VARCHAR PRIMARY KEY,
  camera_id VARCHAR REFERENCES cameras(id),
  profile_id VARCHAR REFERENCES profiles(id),
  timestamp TIMESTAMP NOT NULL,
  status VARCHAR,  -- recognized, unknown, flagged
  confidence FLOAT,
  liveness_score FLOAT,
  age INTEGER,
  gender VARCHAR,
  bbox VARCHAR  -- JSON: [x1, y1, x2, y2]
);
```

### **Alerts Table**
```sql
CREATE TABLE alerts (
  id VARCHAR PRIMARY KEY,
  camera_id VARCHAR REFERENCES cameras(id),
  profile_id VARCHAR REFERENCES profiles(id),
  detection_id VARCHAR REFERENCES detections(id),
  timestamp TIMESTAMP NOT NULL,
  severity VARCHAR,  -- critical, high, medium
  reason VARCHAR,
  acknowledged BOOLEAN DEFAULT FALSE
);
```

---

## 🔄 Data Flow: CSV to Dashboard

### **1. Capture & Detect**
```
Camera → detector.py → detections.csv
└─ Each detection logged with: timestamp, camera, bbox, identity, confidence
```

### **2. Import to Database**
```python
# Script: backend/tasks.py (TO CREATE)
import pandas as pd
detections_df = pd.read_csv('detections.csv')
for _, row in detections_df.iterrows():
    detection = Detection(
        camera_id=row['camera_id'],
        timestamp=row['timestamp'],
        profile_id=match_gallery(row['identity']),
        confidence=row['confidence'],
        bbox=row['bbox']
    )
    db.add(detection)
db.commit()
```

### **3. API Serves Data**
```
FastAPI → SELECT * FROM detections
└─ Returns JSON with camera/profile relationships
```

### **4. WebSocket Broadcasts**
```
New detection logged
└─ Broadcast to /ws/alerts
└─ Frontend receives & updates dashboard in real-time
```

### **5. Dashboard Updates**
```
React Query + WebSocket
├─ Polls /api/kpis every 10 seconds
├─ Listens to /ws/alerts for instant notifications
└─ Updates charts, tables, alerts in real-time
```

---

## 📊 Frontend Updates Needed

Update `facial-recognition-dashboard/lib/api.ts`:

```typescript
// Replace mock functions with real API calls

export const fetchKpis = () =>
  fetch('http://localhost:8000/api/kpis').then(r => r.json())

export const fetchCameras = () =>
  fetch('http://localhost:8000/api/cameras').then(r => r.json())

export const fetchFaceLogs = () =>
  fetch('http://localhost:8000/api/logs?limit=100').then(r => r.json())

export const fetchAlerts = () =>
  fetch('http://localhost:8000/api/alerts?limit=50').then(r => r.json())

export const fetchProfiles = () =>
  fetch('http://localhost:8000/api/profiles').then(r => r.json())

// WebSocket for real-time alerts
export const connectAlertsWebSocket = (onMessage) => {
  const ws = new WebSocket('ws://localhost:8000/ws/alerts')
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    onMessage(data.data)
  }
  return ws
}
```

---

## 🎯 Next Steps

- [ ] Install PostgreSQL locally
- [ ] Create `facial_recognition` database
- [ ] Run `./run-backend.ps1` → `http://localhost:8000/docs`
- [ ] Run `./run-frontend.ps1` → `http://localhost:3000`
- [ ] Update `frontend/lib/api.ts` with real endpoints
- [ ] Import CSV data: `python backend/tasks/ingest_csv.py`
- [ ] Test WebSocket: `wscat -c ws://localhost:8000/ws/alerts`
- [ ] Enable camera feed integration

---

## 📝 Status

| Component | Status | Notes |
|-----------|--------|-------|
| Backend API | ✅ Ready | 10+ endpoints |
| WebSocket | ✅ Ready | 3 channels |
| Database Models | ✅ Ready | PostgreSQL + pgvector |
| Frontend | ⚠️ Mock Data | Needs API integration |
| CSV Import | 📅 TODO | Create ingest script |
| Live Camera Feed | 📅 TODO | RTSP/HLS integration |
| Analytics | 📅 TODO | Footfall, demographics |

---

## 🐛 Troubleshooting

**"Connection refused"**
```
Backend not running? Run: python backend/main.py
```

**"Database connection failed"**
```
PostgreSQL not running? Start: pg_ctl -D "C:\Program Files\PostgreSQL\data" start
Or use PgAdmin to verify connection
```

**"CORS error in frontend"**
```
Check backend/.env has correct CORS_ORIGINS for your frontend URL
```

**"WebSocket connection failed"**
```
Verify ws://localhost:8000/ws/alerts is accessible
Check browser console for errors
```

---

## 📚 References

- [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)
- [pgvector for PostgreSQL](https://github.com/pgvector/pgvector)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/20/)
- [React Query](https://tanstack.com/query/latest)
- [Next.js Documentation](https://nextjs.org/docs)
