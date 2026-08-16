# 🚀 Quick Reference: Development & Deployment

## 🏠 Local Development

### Start Everything

**Terminal 1 - Backend:**
```powershell
cd c:\Users\mkiru\facial\backend

# If using local PostgreSQL
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/facial_recognition"
python main.py
```

**Terminal 2 - Frontend:**
```powershell
cd c:\Users\mkiru\facial\facial-recognition-dashboard
pnpm dev
# OR
npm run dev
```

Visit: **http://localhost:3000**

---

## ☁️ Cloud Deployment (Supabase + Render + Vercel)

### Prerequisites
- GitHub account with code pushed
- Supabase project created
- Render account
- Vercel account

### 1️⃣ Backend → Render

```bash
# 1. Create render.yaml in backend/ (already done)
# 2. Push to GitHub
git push

# 3. Go to https://render.com
# 4. Create New → Web Service
#    - Select your repo
#    - Name: facial-api
#    - Runtime: Python 3.11
#    - Build: pip install -r requirements.txt
#    - Start: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
#    - Add DATABASE_URL from Supabase
# 5. Deploy

# 6. Test
curl https://facial-api.onrender.com/health
```

### 2️⃣ Frontend → Vercel

```bash
# 1. Create .env.production in facial-recognition-dashboard/
NEXT_PUBLIC_API_URL=https://facial-api.onrender.com
NEXT_PUBLIC_WS_URL=wss://facial-api.onrender.com

# 2. Push to GitHub
git push

# 3. Go to https://vercel.com
# 4. Import → Select your repo
#    - Framework: Next.js (auto)
#    - Root: facial-recognition-dashboard
#    - Build: pnpm build (or npm run build)
#    - Add same env vars as above
# 5. Deploy

# 6. Visit https://yourproject.vercel.app
```

### 3️⃣ Database → Supabase

```sql
-- Run in Supabase SQL Editor

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables (see DEPLOYMENT_GUIDE.md for full SQL)
CREATE TABLE cameras (...);
CREATE TABLE profiles (...);
CREATE TABLE embeddings (...);
-- etc...
```

---

## 📊 Load Data into Supabase

### From Local Machine

```powershell
$env:DATABASE_URL = "postgresql://postgres:PASSWORD@db.REGION.supabase.co:5432/postgres"

python backend/tasks/ingest_csv.py --database-url $env:DATABASE_URL
```

**Or with file path:**
```powershell
python backend/tasks/ingest_csv.py `
  --database-url $env:DATABASE_URL `
  --csv-path C:\Users\mkiru\facial\detections.csv
```

---

## 📡 API Endpoints

### Health
```
GET http://localhost:8000/health
→ {"status": "ok"}
```

### System KPIs
```
GET /api/kpis
→ {
  "total_detections": 4866,
  "unique_individuals": 12,
  "cameras_online": 3,
  "critical_alerts": 2
}
```

### Cameras
```
GET /api/cameras
→ [{
  "id": "webcam",
  "name": "Main Lobby",
  "status": "online",
  "fps": 24,
  "gpu_load": 62.0
}]
```

### Detection Logs
```
GET /api/logs?limit=100&offset=0
→ [{
  "id": "...",
  "camera_id": "webcam",
  "timestamp": "2026-08-14T...",
  "confidence": 0.95,
  "profile_name": "Kiru"
}]
```

### Alerts
```
GET /api/alerts?limit=50
→ [{
  "severity": "high",
  "reason": "Blacklist match",
  "acknowledged": false
}]
```

### Full API Docs
```
GET /docs
→ Swagger UI at http://localhost:8000/docs
```

---

## 🔌 WebSocket Connections

### From Browser Console

```javascript
// Alerts channel
const ws = new WebSocket('ws://localhost:8000/ws/alerts')
ws.onmessage = (e) => console.log(JSON.parse(e.data))

// Cameras channel
const ws = new WebSocket('ws://localhost:8000/ws/cameras')

// KPIs channel
const ws = new WebSocket('ws://localhost:8000/ws/kpis')
```

### From React (Frontend)

```typescript
import { connectAlertsWebSocket, API_URL } from '@/lib/api'

// Connect to alerts
const ws = connectAlertsWebSocket((data) => {
  console.log('New alert:', data)
  // Update UI
})

// Cleanup
window.addEventListener('beforeunload', () => ws.close())
```

---

## 🗂️ Project Structure

```
facial/
├── facial_recognition/              # Core ML system
│   ├── detector.py
│   ├── recognizer.py
│   ├── main.py, main_cpu.py
│   └── ...
│
├── backend/                         # FastAPI REST + WebSocket
│   ├── main.py                      # App entry point
│   ├── models.py                    # SQLAlchemy ORM
│   ├── schemas.py                   # Pydantic validation
│   ├── database.py                  # Connection
│   ├── websocket.py                 # Real-time broadcast
│   ├── config.py                    # Environment config
│   ├── tasks/
│   │   └── ingest_csv.py            # Data import script
│   ├── render.yaml                  # Render deployment config
│   ├── requirements.txt
│   ├── .env                         # Local development vars
│   └── __init__.py
│
├── facial-recognition-dashboard/   # Next.js Frontend
│   ├── app/                         # Next.js pages
│   ├── lib/
│   │   ├── api.ts                  # Live API client (UPDATED)
│   │   ├── types.ts                # TypeScript models
│   │   └── mock-data.ts            # Fallback mock data
│   ├── components/                 # React components
│   ├── .env.local                  # Local dev vars
│   ├── .env.local.example
│   └── package.json
│
├── known_faces/                    # Gallery directory
├── cascades/                       # Haar cascade XMLs
├── config.yaml                     # System configuration
├── detections.csv                  # Detection logs (to import)
│
├── run.py, run_cpu.py             # Entry points
├── run-backend.ps1                # Backend launcher
├── run-frontend.ps1               # Frontend launcher
├── setup-all.ps1                  # Full setup
│
├── BACKEND_SETUP.md               # Backend guide
├── DEPLOYMENT_GUIDE.md            # Cloud deployment walkthrough
├── DEPLOYMENT_CHECKLIST.ps1       # Step-by-step checklist
└── README.md
```

---

## 🔑 Environment Variables

### Backend (`backend/.env`)
```ini
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/facial_recognition
CORS_ORIGINS=http://localhost:3000
DEBUG=True
HOST=0.0.0.0
PORT=8000
```

### Backend (Render)
```ini
DATABASE_URL=postgresql://postgres:PASSWORD@db.REGION.supabase.co:5432/postgres
CORS_ORIGINS=https://yourapp.vercel.app
DEBUG=False
PORT=8000
```

### Frontend (`.env.local`)
```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

### Frontend (Vercel)
```ini
NEXT_PUBLIC_API_URL=https://facial-api.onrender.com
NEXT_PUBLIC_WS_URL=wss://facial-api.onrender.com
```

---

## 🐛 Troubleshooting

### "Connection refused" (Backend not running)
```
Run: python backend/main.py
```

### "Database connection failed"
```
Check DATABASE_URL is correct
For Supabase, verify extension: CREATE EXTENSION IF NOT EXISTS vector;
```

### "CORS error" in frontend
```
Update CORS_ORIGINS in backend/.env or Render env vars
Include your frontend URL (e.g., https://yourapp.vercel.app)
```

### "WebSocket connection failed"
```
Use wss:// for production (secure)
Use ws:// for localhost
Check NEXT_PUBLIC_WS_URL is correct
```

### "Empty dashboard"
```
1. Import CSV: python backend/tasks/ingest_csv.py --database-url "..."
2. Verify in Supabase dashboard
3. Check API response: curl http://localhost:8000/api/logs
```

---

## ✅ Checklist: Local → Cloud

### Local Testing (5 min)
- [ ] Run backend: `.\run-backend.ps1`
- [ ] Run frontend: `.\run-frontend.ps1`
- [ ] Visit http://localhost:3000
- [ ] Check API: http://localhost:8000/docs

### Supabase Setup (5 min)
- [ ] Create project at supabase.com
- [ ] Copy connection string
- [ ] Enable pgvector extension
- [ ] Create tables (SQL from DEPLOYMENT_GUIDE.md)

### Backend → Render (15 min)
- [ ] Push to GitHub
- [ ] Create Render service
- [ ] Set DATABASE_URL env var
- [ ] Test: curl https://api.render.com/health

### Frontend → Vercel (10 min)
- [ ] Update .env.production
- [ ] Import to Vercel
- [ ] Set NEXT_PUBLIC_* env vars
- [ ] Test: visit https://app.vercel.app

### Final Integration (5 min)
- [ ] Update Render CORS_ORIGINS with Vercel URL
- [ ] Test WebSocket connection
- [ ] Verify API calls in DevTools
- [ ] Load CSV data if needed

---

## 🎉 Success Criteria

- ✅ Frontend loads at https://yourapp.vercel.app
- ✅ API responds at https://api.render.com/docs
- ✅ WebSocket connects without errors
- ✅ Dashboard shows real data (or mock data loading)
- ✅ Alerts appear in real-time
- ✅ Browser console has no errors

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| `BACKEND_SETUP.md` | Backend architecture & local setup |
| `DEPLOYMENT_GUIDE.md` | Complete cloud deployment walkthrough |
| `DEPLOYMENT_CHECKLIST.ps1` | Interactive checklist |
| `QUICK_REFERENCE.md` | This file |

---

## 🚀 Ready?

1. **Local Dev**: `.\run-backend.ps1` + `.\run-frontend.ps1`
2. **Cloud Deploy**: Follow DEPLOYMENT_CHECKLIST.ps1
3. **Load Data**: `python backend/tasks/ingest_csv.py --database-url "..."`

Questions? Check the docs or API swagger at `/docs` 🎥
