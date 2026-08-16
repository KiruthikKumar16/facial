# 🚀 Deployment Guide: Supabase + Render + Vercel

Complete walkthrough for deploying the facial recognition system to the cloud.

---

## 📋 Overview

```
┌──────────────────────────────────────┐
│  Vercel (Frontend)                   │
│  https://yourapp.vercel.app          │
│  - Next.js 16, React 19              │
│  - Automatic deploys on git push     │
└────────────┬─────────────────────────┘
             │ HTTPS
             ↓
┌──────────────────────────────────────┐
│  Render (Backend API)                │
│  https://facial-api.render.com       │
│  - FastAPI + Uvicorn                 │
│  - WebSocket support                 │
│  - Environment variables             │
└────────────┬─────────────────────────┘
             │ HTTPS (psycopg2-binary)
             ↓
┌──────────────────────────────────────┐
│  Supabase (PostgreSQL + pgvector)    │
│  - Cloud database (free tier: 500MB) │
│  - Built-in pgvector extension       │
│  - Automatic backups                 │
└──────────────────────────────────────┘
```

---

## 💾 Step 1: Supabase Setup (5 minutes)

### 1.1 Create Supabase Project

1. Go to **https://supabase.com** → Click **Sign Up**
2. Use GitHub or email → Verify
3. Click **New Project**
   - **Name**: `facial-recognition`
   - **Region**: Choose closest to you
   - **Postgres Version**: 15 (default)
   - **Password**: Generate strong password → **Save it**
4. Wait 2-3 minutes for provisioning

### 1.2 Get Connection String

1. Go to **Settings → Database**
2. Copy **Connection string → Postgres → URI**
   ```
   postgresql://postgres:PASSWORD@db.REGION.supabase.co:5432/postgres
   ```
3. Save this for later (needs to be in Render env vars)

### 1.3 Enable pgvector

1. Go to **SQL Editor**
2. New Query → Paste:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Run Query
4. Verify success message

### 1.4 Create Tables

Run this SQL in Supabase SQL Editor:

```sql
-- Cameras table
CREATE TABLE cameras (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  zone VARCHAR,
  ip_address VARCHAR,
  rtsp_url VARCHAR,
  status VARCHAR,
  ping_ms INTEGER DEFAULT 0,
  frame_latency_ms INTEGER DEFAULT 0,
  fps FLOAT DEFAULT 0.0,
  gpu_load FLOAT DEFAULT 0.0,
  cpu_load FLOAT DEFAULT 0.0,
  last_heartbeat TIMESTAMP,
  detections_today INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Profiles (gallery)
CREATE TABLE profiles (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  role VARCHAR DEFAULT 'visitor',
  department VARCHAR,
  embedding_status VARCHAR DEFAULT 'pending',
  embedding_count INTEGER DEFAULT 0,
  enrolled_at TIMESTAMP DEFAULT NOW(),
  last_seen TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Face embeddings (512-dim vectors)
CREATE TABLE embeddings (
  id VARCHAR PRIMARY KEY,
  profile_id VARCHAR REFERENCES profiles(id) ON DELETE CASCADE,
  vector vector(512),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create index for similarity search
CREATE INDEX embeddings_vector_idx ON embeddings USING ivfflat (vector vector_cosine_ops);

-- Detections (face logs)
CREATE TABLE detections (
  id VARCHAR PRIMARY KEY,
  camera_id VARCHAR REFERENCES cameras(id),
  profile_id VARCHAR REFERENCES profiles(id),
  timestamp TIMESTAMP NOT NULL,
  status VARCHAR DEFAULT 'unknown',
  confidence FLOAT DEFAULT 0.0,
  liveness_score FLOAT DEFAULT 0.0,
  age INTEGER,
  gender VARCHAR DEFAULT 'unknown',
  wearing_mask BOOLEAN DEFAULT FALSE,
  wearing_glasses BOOLEAN DEFAULT FALSE,
  bbox VARCHAR,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Alerts
CREATE TABLE alerts (
  id VARCHAR PRIMARY KEY,
  detection_id VARCHAR REFERENCES detections(id),
  camera_id VARCHAR REFERENCES cameras(id),
  profile_id VARCHAR REFERENCES profiles(id),
  timestamp TIMESTAMP NOT NULL,
  severity VARCHAR,
  reason VARCHAR,
  acknowledged BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Model thresholds
CREATE TABLE model_thresholds (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL UNIQUE,
  value FLOAT NOT NULL,
  description VARCHAR,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX cameras_status_idx ON cameras(status);
CREATE INDEX profiles_name_idx ON profiles(name);
CREATE INDEX detections_timestamp_idx ON detections(timestamp);
CREATE INDEX detections_camera_idx ON detections(camera_id);
CREATE INDEX detections_profile_idx ON detections(profile_id);
CREATE INDEX alerts_camera_idx ON alerts(camera_id);
CREATE INDEX alerts_severity_idx ON alerts(severity);
```

---

## 🖥️ Step 2: Deploy Backend to Render (10 minutes)

### 2.1 Push to GitHub

```powershell
cd c:\Users\mkiru\facial

# Initialize git (if not already)
git init
git add .
git commit -m "Initial commit: facial recognition system"
git branch -M main

# Add remote
git remote add origin https://github.com/YOUR_USERNAME/facial.git
git push -u origin main
```

### 2.2 Deploy to Render

1. Go to **https://render.com** → Sign up with GitHub
2. Click **New** → **Web Service**
3. Select your GitHub repo
4. **Name**: `facial-api`
5. **Environment**: `Python 3.11`
6. **Build Command**:
   ```
   pip install -r backend/requirements.txt
   ```
7. **Start Command**:
   ```
   cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
8. **Environment Variables**:
   - `DATABASE_URL`: Paste Supabase connection string
   - `CORS_ORIGINS`: `https://yourfrontend.vercel.app` (will get this after Vercel deploy)
   - `DEBUG`: `False`

9. Click **Create Web Service**
10. Wait 3-5 minutes for deployment
11. Copy your service URL: `https://facial-api.onrender.com`

### 2.3 Test Backend

```powershell
# Health check
curl https://facial-api.onrender.com/health

# Should return: {"status": "ok", "timestamp": "..."}

# View API docs
# Visit: https://facial-api.onrender.com/docs
```

---

## 🎨 Step 3: Deploy Frontend to Vercel (10 minutes)

### 3.1 Update Environment Variables

Create `.env.production` in `facial-recognition-dashboard/`:

```
NEXT_PUBLIC_API_URL=https://facial-api.onrender.com
NEXT_PUBLIC_WS_URL=wss://facial-api.onrender.com
```

### 3.2 Deploy to Vercel

1. Go to **https://vercel.com** → Sign up with GitHub
2. Click **Add New** → **Project**
3. Select your GitHub repo
4. **Framework**: Next.js (auto-detected)
5. **Root Directory**: `facial-recognition-dashboard`
6. **Build Command**: `pnpm build` (or `npm run build`)
7. **Output Directory**: `.next`
8. **Environment Variables**:
   - `NEXT_PUBLIC_API_URL=https://facial-api.onrender.com`
   - `NEXT_PUBLIC_WS_URL=wss://facial-api.onrender.com`
9. Click **Deploy**
10. Wait 2-3 minutes
11. Copy your frontend URL: `https://yourproject.vercel.app`

### 3.3 Update Backend CORS

1. Go to **Render → facial-api → Environment**
2. Update `CORS_ORIGINS` to include your Vercel URL:
   ```
   https://yourproject.vercel.app,https://www.yourproject.vercel.app
   ```
3. Click **Save Changes** (auto-redeploys)

---

## 🧪 Step 4: Test End-to-End

### 4.1 Test API Endpoints

```bash
# Health check
curl https://facial-api.onrender.com/health

# Get KPIs (empty until you load data)
curl https://facial-api.onrender.com/api/kpis

# Get cameras
curl https://facial-api.onrender.com/api/cameras

# Get profiles
curl https://facial-api.onrender.com/api/profiles
```

### 4.2 Test Frontend

1. Open **https://yourproject.vercel.app**
2. Should show dashboard (with empty data)
3. Open browser console (F12) → check for API errors
4. If successful, API URL should appear in Network tab

### 4.3 Test WebSocket

```javascript
// In browser console
const ws = new WebSocket('wss://facial-api.onrender.com/ws/alerts')
ws.onopen = () => console.log('✓ WebSocket connected')
ws.onmessage = (event) => console.log('Message:', event.data)
```

---

## 📊 Step 5: Load Data

### 5.1 Import CSV to Supabase

Create `backend/tasks/ingest_csv.py`:

```python
import pandas as pd
from sqlalchemy import create_engine
import os
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# Load CSV
df = pd.read_csv('../detections.csv')

# Parse timestamps
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Prepare detection records
detections = []
for idx, row in df.iterrows():
    detection = {
        'id': f"det_{idx}",
        'camera_id': row['camera_id'],
        'profile_id': None,  # TODO: match with gallery
        'timestamp': row['timestamp'],
        'status': 'unknown' if row['identity'] == 'Unknown' else 'recognized',
        'confidence': row['confidence'],
        'liveness_score': 0.0,
        'bbox': str(row['bbox']),
    }
    detections.append(detection)

# Insert via SQL
with engine.connect() as conn:
    for det in detections:
        conn.execute(
            "INSERT INTO detections (id, camera_id, profile_id, timestamp, status, confidence, liveness_score, bbox) "
            "VALUES (:id, :camera_id, :profile_id, :timestamp, :status, :confidence, :liveness_score, :bbox)",
            det
        )
    conn.commit()

print(f"✓ Imported {len(detections)} detections")
```

Run locally:
```powershell
$env:DATABASE_URL = "postgresql://..."  # Supabase connection string
python backend/tasks/ingest_csv.py
```

---

## 📝 Environment Variables Summary

### **Render Backend**
```
DATABASE_URL=postgresql://postgres:PASSWORD@db.REGION.supabase.co:5432/postgres
CORS_ORIGINS=https://yourproject.vercel.app
DEBUG=False
PORT=8000
```

### **Vercel Frontend**
```
NEXT_PUBLIC_API_URL=https://facial-api.onrender.com
NEXT_PUBLIC_WS_URL=wss://facial-api.onrender.com
```

---

## 🔄 Development Workflow

### **Local Testing**
```powershell
# Terminal 1: Backend
$env:DATABASE_URL = "postgresql://localhost:5432/..."
.\run-backend.ps1

# Terminal 2: Frontend
.\run-frontend.ps1
```

### **Cloud Deployment**
```powershell
# Push to GitHub
git add .
git commit -m "Update features"
git push

# Render auto-deploys backend
# Vercel auto-deploys frontend
# (Automatic on every push)
```

---

## 🐛 Troubleshooting

### **"CORS error" in console**
- Check Render env var `CORS_ORIGINS` includes your Vercel URL
- Render may take 1-2 minutes to restart after env change

### **"Database connection failed"**
- Verify Supabase connection string is correct
- Check that pgvector extension is enabled in Supabase
- Render logs: Dashboard → Settings → Logs

### **"WebSocket connection refused"**
- Use `wss://` (secure) not `ws://`
- Ensure backend supports WebSocket on Render (FastAPI does)
- Check browser console for actual error

### **"Empty dashboard / no data**"
- Data needs to be imported from CSV
- Run `ingest_csv.py` script with Supabase credentials
- Verify data in Supabase dashboard → SQL Editor

---

## 💰 Pricing (Free Tier)

| Service | Free Tier | Cost |
|---------|-----------|------|
| **Supabase** | 500MB DB, 2 projects | $25/mo after |
| **Render** | Web service (750 hours/month) | $7/mo after |
| **Vercel** | Unlimited deployments | $20/mo for Pro |
| **Total** | **$0** | **~$52/mo** |

---

## ✅ Checklist

- [ ] Supabase project created
- [ ] pgvector extension enabled
- [ ] Database tables created
- [ ] Code pushed to GitHub
- [ ] Backend deployed to Render
- [ ] Backend health check passing
- [ ] Frontend deployed to Vercel
- [ ] Environment variables set (Vercel + Render)
- [ ] CORS configured correctly
- [ ] WebSocket test successful
- [ ] CSV data imported to Supabase
- [ ] Dashboard showing live data

---

## 🎉 You're Live!

Once everything passes, your system is running in the cloud:
- **Frontend**: https://yourproject.vercel.app
- **API Docs**: https://facial-api.onrender.com/docs
- **Database**: Supabase console
- **Real-time**: WebSocket alerts working

Enjoy your surveillance system! 🎥
