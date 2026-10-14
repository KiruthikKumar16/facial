# Distributed Deployment Guide: Vercel + JarvisLabs + Supabase

This architecture distributes components across their ideal hosting environments:
- **Frontend**: **Vercel** (Global CDN, fast Next.js SSR & static edge hosting)
- **Backend & Detection**: **JarvisLabs** (Dedicated NVIDIA Cloud GPU instance, FastAPI + Redis + InsightFace)
- **Database**: **Supabase** (Managed PostgreSQL + pgvector cloud database)

```
                       +----------------------------------+
                       |       Vercel (Next.js)           |
                       |  https://your-dashboard.vercel.app
                       +-----------------+----------------+
                                         |
                       HTTPS REST / WSS  | (Port 1223)
                                         v
+-------------------------------------------------------------------------------+
|                            JarvisLabs (Cloud GPU)                             |
|                                                                               |
|   +-----------------------+     Pub/Sub      +----------------------------+   |
|   |  facial_backend       | <--------------> |  facial_redis (redis:7)    |   |
|   |  (FastAPI on :1223)   |                  +----------------------------+   |
|   +-----------+-----------+                                                   |
|               ^                                                               |
|   POST /events| (Docker Internal Network)                                     |
|   +-----------+-----------+                                                   |
|   |  facial_detector      |                                                   |
|   |  (NVIDIA GPU ArcFace) | <--- RTSP Stream(s) / IP Cameras                  |
|   +-----------------------+      OR local PC webcam via frame sender          |
+---------------------------------------+---------------------------------------+
                                        |
                 PostgreSQL + pgvector  | (Port 5432 SSL)
                                        v
                       +----------------------------------+
                       |       Supabase Cloud DB          |
                       |  aws-0-ap-southeast-1.pooler...  |
                       +----------------------------------+
```

---

## Part 1: Supabase (Database)
Your database is already provisioned and configured:
- **Connection URL**:
  ```text
  postgresql://postgres.hdiqjkhcavdmymusyfbh:BooseCat%40123@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
  ```
- **Extensions**: `pgvector` enabled, all tables (`profiles`, `embeddings`, `detections`, `alerts`, `unregistered_subjects`) are initialized.

---

## Part 2: JarvisLabs (Backend + GPU Detection + Redis)

### 1. Launch Instance on JarvisLabs
1. Select a GPU instance (e.g. **RTX 4090**, **A100**, or **RTX 5000 Ada**).
2. Framework: Choose **PyTorch** or **CUDA 12.x**.
3. **Expose Port**: In the JarvisLabs instance settings, expose HTTP port **1223** (this creates your public HTTPS URL).
4. Open the **Terminal** in JarvisLabs (via SSH or Jupyter terminal).

### 2. Clone the Repository
```bash
git clone <your-github-repo-url> facial
cd facial
```

### 3. Create `.env` on JarvisLabs
Create `.env` in the repository root:
```bash
cat << 'EOF' > .env
DATABASE_URL=postgresql://postgres.hdiqjkhcavdmymusyfbh:BooseCat%40123@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
REDIS_URL=redis://redis:6379/0
PORT=1223
SECRET_KEY=0963d6d35cc4d8b90f7524681cfb813fc14811d4b6cc65ff649402329de418ec
EDGE_API_KEY=4349000f7201d2db0193e1cec0fc42341837486915fab5a4802fd1371ac0c6dd
ADMIN_PASSWORD=kiru1223
ENABLE_FORENSIC_SEARCH=true
APP_TIMEZONE=Asia/Kolkata
TZ=Asia/Kolkata

# Allow your Vercel domain and localhost
CORS_ORIGINS=https://*.vercel.app,http://localhost:3000
EOF
```

### 4. Start the Services on JarvisLabs
Use the dedicated JarvisLabs compose file:
```bash
docker compose -f docker-compose.jarvislabs.yml up -d --build
```

Verify all 3 containers are running:
```bash
docker compose -f docker-compose.jarvislabs.yml ps
```
You will see:
- `facial_redis` (healthy)
- `facial_backend` (healthy)
- `facial_detector` (running with GPU reservation)

### 5. Get Your JarvisLabs Public Backend URL
In the JarvisLabs dashboard, locate your running instance:
- Look at the exposed HTTP port for `1223`. JarvisLabs assigns a public URL format like:
  `https://<instance-id>-1223.jarvislabs.run` (or an IP and port).
- Verify in browser or terminal:
  ```bash
  curl https://<your-jarvislabs-url>/health
  # Returns: {"status": "ok", "timestamp": "..."}
  ```

---

## Part 3: Vercel (Frontend Next.js Dashboard)

### 1. Import Project to Vercel
1. Go to [Vercel Dashboard](https://vercel.com).
2. Click **Add New...** &rarr; **Project**.
3. Import your GitHub repository.
4. Set **Root Directory** to:
   ```text
   facial-recognition-dashboard
   ```

### 2. Configure Environment Variables on Vercel
In the Vercel **Environment Variables** section, add:

| Key | Value | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<your-jarvislabs-url>` | JarvisLabs backend HTTPS URL (no trailing slash) |
| `NEXT_PUBLIC_WS_URL` | `wss://<your-jarvislabs-url>` | JarvisLabs backend WSS WebSocket URL |

*Example:*
- `NEXT_PUBLIC_API_URL` = `https://abc1234-1223.jarvislabs.run`
- `NEXT_PUBLIC_WS_URL` = `wss://abc1234-1223.jarvislabs.run`

### 3. Deploy
Click **Deploy**. Vercel will build and deploy the Next.js application to:
`https://<your-app-name>.vercel.app`

### 4. Update CORS on JarvisLabs (if needed)
If your Vercel domain is `https://my-facial-dashboard.vercel.app`, ensure it is included in `.env` on JarvisLabs:
```bash
CORS_ORIGINS=https://my-facial-dashboard.vercel.app,https://*.vercel.app,http://localhost:3000
```
Then restart backend:
```bash
docker compose -f docker-compose.jarvislabs.yml restart backend
```

---

## Part 4: Camera Video Feeds

### Option A: IP Cameras / CCTV / NVR / DVR (Direct RTSP)
Configure your RTSP URLs in `facial_recognition/config.yaml` on JarvisLabs:
```yaml
rtsp_urls:
  - rtsp://admin:password@camera-ip:554/stream1
```
The `facial_detector` container automatically ingests and processes the stream on the GPU.

### Option B: Local Laptop USB Webcam
Because JarvisLabs is in the cloud and cannot access your physical laptop USB webcam:
1. On your local laptop, run the frame sender pointing to JarvisLabs:
   ```bash
   python facial_recognition/pc_frame_sender.py
   ```
   Set `REMOTE_DETECTION_URL` in `.env` or pass CLI flags to stream frames to JarvisLabs for instant GPU inference.
