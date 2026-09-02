# 🌟 Facial Recognition System - Final Report

## 📖 Executive Summary
This repository contains a full-stack, enterprise-grade Facial Recognition, Security, and Analytics platform. It consists of three tightly integrated components:
1. **`facial_recognition/` (Core AI & CV Pipeline):** A Python-based computer vision application utilizing `insightface`, `onnxruntime`, and OpenCV to extract 512-dimensional face embeddings from webcam or RTSP streams.
2. **`backend/` (FastAPI Server):** A scalable REST & WebSocket API built on FastAPI and PostgreSQL (`pgvector`), orchestrating the data layer and running server-side ML queries.
3. **`facial-recognition-dashboard/` (Next.js Frontend):** A beautiful, modern, real-time React dashboard utilizing `@tanstack/react-query`, Shadcn UI, and WebSocket bindings to visualize system health, alerts, and analytics.

---

## 🏗️ Architecture & Three-Tier Setup

### 1. Computer Vision Pipeline (Local Edge)
- **Engine**: Uses `InsightFace` (buffalo_l) via ONNX Runtime to detect and extract face embeddings.
- **Dual-Write Logging**: Designed to run continuously on a local machine (`run.ps1` or `run_cpu.ps1`), writing detections simultaneously to a local `detections.csv` archive and instantly over the network to the PostgreSQL database.
- **Resilience**: Features robust fallback mechanisms if the database drops connection, ensuring no frames or events are lost.

### 2. Backend API (Cloud - Render)
- **Tech Stack**: FastAPI, SQLAlchemy, Uvicorn, PostgreSQL with `pgvector`.
- **Database Models**: 
  - `cameras`, `profiles`, `embeddings`, `detections`, `alerts`, `model_thresholds`.
- **AI Integration**: Imports the `InsightFaceDetector` directly from the `facial_recognition` module. By injecting this logic into the FastAPI `lifespan`, the backend natively processes manual uploads for Forensic Search and Profile Enrollments without spinning up external microservices.
- **Vector Search**: Leverages `pgvector` Cosine Distance (`<=>`) to execute ultra-fast face similarity searches directly inside the SQL engine.
- **Real-Time Data**: Exposes `/ws/alerts`, `/ws/cameras`, and `/ws/kpis` WebSocket channels to push live telemetry.

### 3. Frontend Dashboard (Cloud - Vercel)
- **Tech Stack**: Next.js 14, React 18, TailwindCSS, Lucide Icons, `@tanstack/react-query`.
- **Tabs**:
  1. **Alerts**: Real-time event log and alert management.
  2. **Forensic Search**: Upload a photo to search the database for matches against historic detections.
  3. **Profiles**: Vector database management, identity enrollment, and duplicate merging.
  4. **Analytics**: Rich interactive charts for Footfall, Trajectory, Age/Gender Demographics, and Attendance.
  5. **System Health**: Hardware telemetry and model threshold configuration.
- **Hardening**: Implements a global `ErrorBoundary` architecture ensuring localized widget crashes never cascade to the main UI.

---

## 🚀 Deployment Topology

The application is fully configured for a distributed cloud architecture:

### 1. Database (Supabase)
- Hosts the PostgreSQL instance with the `pgvector` extension enabled.
- Stores all detection events, alert configurations, and the 512-dim embedding arrays.

### 2. Backend (Render)
- Deployed as a Python Web Service.
- Reads `DATABASE_URL` from the environment to connect to Supabase.
- The `requirements.txt` specifically includes `opencv-python-headless`, `onnxruntime`, and `insightface` to allow Render's headless Linux environment to run the AI embedding models natively on the backend.
- Applies Security Middleware (HSTS, `X-Content-Type-Options`) and strict CORS configurations (`CORS_ORIGINS`).

### 3. Frontend (Vercel)
- Deployed as a standard Next.js application.
- Configured with `NEXT_PUBLIC_API_URL` pointing to the Render backend and `NEXT_PUBLIC_WS_URL` for the WebSocket connections.

---

## 🔧 Core Workflows

### Live Camera Processing
1. The `facial_recognition` pipeline captures a frame.
2. `InsightFace` detects a face, extracts the embedding, and compares it to known profiles.
3. The event is written to `detections.csv` and inserted directly into the PostgreSQL `detections` table via SQLAlchemy.
4. FastAPI detects the new record and broadcasts it over the `/ws/alerts` WebSocket.
5. The Next.js dashboard receives the WebSocket message, invalidates the React Query cache, and instantly rerenders the new alert on the UI.

### Forensic Search
1. A security officer uploads an image of a suspect on the Next.js dashboard.
2. The image is POSTed to the Render Backend `/api/forensic/search`.
3. The Backend passes the image to the `InsightFaceDetector` to extract the embedding tensor.
4. The Backend queries Supabase: `SELECT * FROM profiles JOIN embeddings WHERE vector <=> [tensor] <= 0.40`.
5. Matching profiles and their associated sightings are returned to the UI.

### Profile Merging (Duplicate Resolution)
1. The Dashboard queries `/api/analytics/duplicates` which performs a high-efficiency Self-Join on the `embeddings` table to find different `profile_id`s with a vector cosine distance `< 0.1` (>90% similar).
2. The UI presents these candidates to the user.
3. The user clicks "Merge", sending a POST to `/api/profiles/merge`.
4. The backend runs a transactional SQL UPDATE, re-parenting all `detections`, `alerts`, and `embeddings` from the duplicate profile to the primary profile, and deletes the duplicate identity.

---

## 🏁 Final Status
- **Backend API**: 100% Implemented (No Mocks).
- **Frontend UI**: 100% Implemented (No Mocks).
- **Computer Vision Model**: 100% Implemented (Integrated into both Edge and Cloud environments).
- **Readiness**: Production Ready.
