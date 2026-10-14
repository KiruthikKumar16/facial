# Deployment Guide — Vercel + JarvisLabs (GPU) + Supabase

This project uses a production-ready, distributed cloud topology with hardware-accelerated AI:

| Component | Platform | Configuration File / Directory |
|:---|:---|:---|
| **Dashboard UI** | **Vercel** | `facial-recognition-dashboard/` |
| **Backend API** | **JarvisLabs / Cloud VM** | `backend/Dockerfile` |
| **GPU Detection Service** | **JarvisLabs / Cloud VM** | `Dockerfile.detector` |
| **Database** | **Supabase** (PostgreSQL + `pgvector`) | Connection String / Transaction Pooler (port 6543) |
| **Edge Video Feeds** | **Local PC / IP Camera** | `facial_recognition/main_cpu.py` or RTSP |

---

## 1. Supabase (Database Setup)

1. Create a project at [supabase.com](https://supabase.com).
2. Enable `pgvector` extension in the Supabase SQL Editor:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Copy your connection string from **Project Settings → Database → Connection string (URI)**.
   * **Important**: Use the Transaction Mode Pooler port `6543` (e.g. `aws-0-...pooler.supabase.com:6543`). The backend automatically rewrites `:5432` pooler URLs to `:6543` if provided.
4. Tables, foreign keys, and HNSW vector indexes (`ix_embeddings_vector_hnsw`, `ix_detections_embedding_vector_hnsw`) are created automatically when the backend boots.

---

## 2. JarvisLabs (Backend & GPU Detection Service)

Deploying to an NVIDIA GPU instance on [JarvisLabs](https://jarvislabs.ai) (RTX 4000, A5000, or A6000):

1. **Launch an Instance**: Select **PyTorch** framework with 1 GPU.
2. **Clone Repository & Configure Environment**:
   ```bash
   git clone https://github.com/KiruthikKumar16/facial.git
   cd facial
   cp .env.example .env
   nano .env
   ```
   * Set `DATABASE_URL` to your Supabase connection string.
   * Set `EDGE_API_KEY` to a secure random token.
   * Set `CORS_ORIGINS` to your Vercel deployment URL (and `http://localhost:3000`).

3. **Start with Docker Compose**:
   ```bash
   docker compose -f docker-compose.jarvislabs.yml up -d --build
   ```
   This launches:
   * **`backend`**: FastAPI REST & WebSocket server on port `1223` (`http://localhost:1223/health`).
   * **`gpu-detector`**: GPU-accelerated InsightFace detection service on port `8000` with full CUDA access.

4. **Expose Ports**:
   * In the JarvisLabs dashboard, expose HTTP port `1223` (or set up a domain endpoint).

---

## 3. Vercel (Next.js Dashboard)

1. Import the repository on [vercel.com](https://vercel.com).
2. Set **Root Directory** to `facial-recognition-dashboard`.
3. Set **Framework Preset** to `Next.js`.
4. Configure Environment Variables:
   * `NEXT_PUBLIC_API_URL` = `https://<YOUR-JARVISLABS-BACKEND-URL>`
   * `NEXT_PUBLIC_WS_URL` = `wss://<YOUR-JARVISLABS-BACKEND-URL>`
5. Click **Deploy**.
6. Ensure your production Vercel domain (e.g., `https://your-dashboard.vercel.app`) is included in `CORS_ORIGINS` on JarvisLabs.

---

## 4. Edge Node / Local Webcam

To push live camera feeds from your local machine to the cloud:

1. Configure `.env`:
   ```env
   API_URL=https://<YOUR-JARVISLABS-BACKEND-URL>
   EDGE_API_KEY=<SAME-EDGE-KEY-AS-BACKEND>
   EDGE_STREAM_FPS=8
   EDGE_STREAM_JPEG_QUALITY=75
   ```
2. Run local camera capture:
   ```powershell
   python facial_recognition\main_cpu.py --max
   ```
   * Frames are captured, faces are analyzed, and detection logs are streamed to the backend via WebSocket & REST.
   * If network connection drops, events are persisted in the local SQLite WAL ledger and synced upon reconnection.

---

## 5. End-to-End Verification Checklist

- [ ] `GET https://<JARVIS-BACKEND>/health` returns `{"status":"ok"}`.
- [ ] Vercel dashboard loads without CORS warnings in browser console.
- [ ] WebSocket connected (`/ws/alerts`, `/ws/kpis`, `/ws/cameras`).
- [ ] Running the edge camera node produces live events in the Alerts and Analytics tabs.
- [ ] Forensic Search extracts embeddings and returns matches against Supabase profiles.

For rapid copy-paste setup commands, refer to [DEPLOY_JARVIS_VERCEL.md](file:///d:/facial/DEPLOY_JARVIS_VERCEL.md).
