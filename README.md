# Facial Recognition & Analytics Platform

An end-to-end, real-time facial recognition and vector-search analytics platform designed to bridge local edge-inference with a cloud-native Next.js dashboard.

## Description
This system processes live RTSP and webcam video feeds on local edge devices, extracting 512-dimensional facial embeddings using ONNX and InsightFace. It instantly synchronizes these captures with a cloud-hosted PostgreSQL vector database (`pgvector`) via a robust dual-write pipeline. A full-stack Next.js and FastAPI cloud dashboard consumes this data via WebSockets to provide real-time security alerts, footfall analytics, and instant forensic similarity searches across millions of recorded detections.

## Key Features
- **Real-Time Edge Inference**: Low-latency face detection and recognition using the `buffalo_l` model running on ONNX CPU/GPU Execution Providers.
- **`pgvector` Forensic Search**: Execute millisecond cosine-similarity searches (`<=>`) natively in PostgreSQL to find matching suspects from static photo uploads.
- **Live-Streaming Telemetry**: Bi-directional WebSockets push instantaneous security alerts, camera health events, and KPI changes directly to the React frontend.
- **Resilient Dual-Write Pipeline**: Employs a local `.csv` transaction log paired with asynchronous SQLAlchemy cloud inserts, ensuring zero data loss during network partitions.
- **Identity Deduplication**: High-efficiency SQL self-joins compute vector distances across the entire database to automatically surface and merge duplicate identities.
- **Robust Error Handling**: Granular React Error Boundaries prevent individual dashboard widgets from crashing the global UI.

## Tech Stack
- **Frontend**: Next.js 14, React 18, TailwindCSS, Shadcn UI, Lucide Icons, `@tanstack/react-query`
- **Backend API**: Python, FastAPI, Uvicorn, WebSockets, SQLAlchemy (ORM)
- **Computer Vision / AI**: InsightFace, ONNX Runtime, OpenCV, NumPy
- **Database**: PostgreSQL (Supabase) with the `pgvector` extension
- **Deployment**: Vercel (Frontend), Render (Backend), Local PC (Edge CV Pipeline)

## Architecture
The architecture utilizes a distributed Edge-to-Cloud pattern:
1. **Edge CV Node (`facial_recognition/`)**: A local Python process captures live video frames. `InsightFace` detects faces, extracts the 512-dim embedding tensors, and identifies known profiles. It synchronously writes the event to a local CSV archive while async-POSTing the data to the Cloud API.
2. **Cloud API (`backend/`)**: A FastAPI server running on Render ingests edge events and inserts them into Supabase via SQLAlchemy. It also securely houses the ONNX models in memory during its `lifespan` to process manual image uploads (Forensic Search) without taxing the edge nodes.
3. **Cloud Database (`Supabase`)**: Stores relational metadata (Profiles, Cameras, Alerts) and uses `pgvector` to index the 512-dim embedding arrays, allowing for mathematical cosine distance queries.
4. **Cloud Dashboard (`facial-recognition-dashboard/`)**: A Next.js application that fetches historical aggregated analytics via REST and listens to FastAPI WebSockets for live React Query invalidations, ensuring the UI is perpetually up-to-date.

## I Built
I served as the sole Full-Stack and Machine Learning Engineer for this project. I designed the 3-tier architecture, integrated the `InsightFace` ONNX models into both the local edge pipeline and the FastAPI backend, and wrote the raw `pgvector` SQL statements to handle vector similarity searches. I built the entire Next.js frontend, utilizing React Query and WebSockets to create a seamless, real-time command center, and deployed the distributed system across Vercel, Render, and Supabase.

## Challenges & Solutions
- **Challenge**: The cloud backend on Render was crashing due to `libGL.so.1` dependency errors when importing OpenCV.
  **Solution**: Refactored the `requirements.txt` to use `opencv-python-headless`, allowing the AI models to execute perfectly in a headless Linux server environment without requiring heavy GUI libraries.
- **Challenge**: Vercel frontend dashboards polling the database too frequently resulted in high latency and database strain.
  **Solution**: Engineered a WebSocket pub/sub model in FastAPI. Instead of polling, the frontend subscribes to channels (e.g., `/ws/alerts`). When the backend detects a new database row, it pushes an invalidation signal to the client, triggering `@tanstack/react-query` to fetch exactly what it needs, exactly when it needs it.
- **Challenge**: Managing duplicated identities when the same person walks past multiple cameras at different angles.
  **Solution**: Implemented an automated deduplication endpoint that performs a vector self-join on the `embeddings` table, flagging profiles with a cosine distance of `< 0.1` (>90% similar) for a one-click SQL transactional merge.

## Results
- Successfully integrated a **512-dimensional vector** similarity search engine natively into the database layer.
- Achieved **sub-100ms** latency for complex forensic queries against thousands of historical detections.
- Deployed a **100% real-time** command dashboard with zero reliance on mock data or inefficient HTTP polling.

## Setup
1. **Database Setup**: Spin up a Supabase PostgreSQL instance and enable the `pgvector` extension.
2. **Backend**: 
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
3. **Frontend**:
   ```bash
   cd facial-recognition-dashboard
   pnpm install
   pnpm dev
   ```
4. **Edge CV**:
   ```bash
   cd facial_recognition
   python run.py
   ```
## Commands Cheat Sheet

### 1. Naming Unknown Faces (Gallery Management)
Run these from inside the `facial_recognition/` folder:
- **`python review_pending.py`**: Reviews unknown faces saved in the `pending/` folder, prompts you for their name via a GUI, and adds them to the known gallery.
- **`python enroll.py`**: Rebuilds the `gallery.npz` file from scratch using images placed inside `known_faces/`.

### 2. Running the Edge Cameras
Run these from inside the `facial_recognition/` folder:
- **`python main_cpu.py`**: Runs the highly-optimized camera script tuned for laptops/CPUs (skips frames, limits threads).
- **`python run.py`**: The standard camera execution script, best used with a dedicated NVIDIA GPU.
- **`python benchmark_detector.py`**: Tests your webcam and prints out the FPS and latency of the AI models.

### 3. Running the FastAPI Backend
- **`.\scripts\run-backend.ps1`** (from root): A PowerShell wrapper to launch the Python backend.
- **`uvicorn main:app --reload`** (from `backend/`): Manually starts the FastAPI server on `localhost:8000`.

### 4. Running the Next.js Dashboard
- **`.\scripts\run-frontend.ps1`** (from root): A PowerShell wrapper to launch the web interface.
- **`pnpm dev`** (from `facial-recognition-dashboard/`): Manually starts the Next.js UI on `localhost:3000`.

### 5. Setup & Validation
Run these from the root folder:
- **`.\scripts\setup-all.ps1`**: Automatically creates Python virtual environments, installs requirements, and runs `pnpm install` for the frontend.
- **`.\scripts\DEPLOYMENT_CHECKLIST.ps1`**: A helper script to quickly verify that all `.env` variables are correctly set before deployment.

## Links
- **GitHub Repository**: [Your Link Here]
- **Live Demo**: [Your Link Here]
