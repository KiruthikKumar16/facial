# Facial Recognition & Analytics Platform - Project Overview

## Directory Structure

```
facial/
├── facial_recognition/          # Core AI & Edge CV Engine
│   ├── known_faces/             # Enrolled faces gallery (.npz and face crops)
│   ├── pending/                 # Stored observations for unrecognized individuals
│   ├── main.py                  # Main entry point (GPU / CUDA accelerated)
│   ├── main_cpu.py              # CPU-optimized edge detection pipeline
│   ├── pc_frame_sender.py       # Frame sender client for remote detector microservices
│   ├── remote_detector.py       # Client for offloaded detection inference
│   ├── enroll.py                # Tool to build gallery embeddings from known_faces/
│   ├── detector.py              # InsightFace (SCRFD + ArcFace) detection wrapper
│   ├── recognizer.py            # Cosine similarity recognition & gallery search
│   ├── logger.py                # Detection logging & cloud sync worker
│   ├── event_ledger.py          # Cryptographic SQLite WAL transaction ledger
│   ├── topology.py              # Physical camera topology & transition graph
│   ├── cross_camera_tracker.py  # Cross-camera identity continuity engine
│   ├── quality.py               # Face anti-spoofing & ISO quality assessor
│   ├── track_fusion.py          # Temporal multi-frame observation fusion
│   ├── config.yaml              # Edge pipeline configuration
│   └── ...
│
├── backend/                     # Cloud / Server API (FastAPI)
│   ├── main.py                  # FastAPI application entrypoint & MJPEG streams
│   ├── models.py                # SQLAlchemy models (pgvector integration)
│   ├── schemas.py               # Pydantic schemas (camelCase serialization)
│   ├── config.py                # Application settings & IST timezone helpers
│   ├── database.py              # PostgreSQL engine & connection pool management
│   ├── auth.py                  # JWT authentication & login endpoints
│   ├── middleware.py            # Security headers & token verification middleware
│   ├── dependencies.py          # API key verification for edge nodes
│   ├── state.py                 # Shared memory frame store & model registry
│   ├── websocket.py             # Distributed WebSocket relay & connection manager
│   ├── routers/                 # Modular API route controllers
│   │   ├── analytics.py         # Footfall, demographics, attendance, trajectory
│   │   ├── cameras.py           # Camera lifecycle & versioned configuration
│   │   ├── detections.py        # Edge detection ingestion & sequence reconciliation
│   │   ├── forensic.py          # Vector forensic image search
│   │   ├── logs.py              # Detection logs & alert acknowledgement
│   │   ├── profiles.py          # Identity enrollment, deletion & profile merging
│   │   ├── system.py            # System KPIs, health checks & version snapshots
│   │   └── unregistered.py      # Unregistered subject clustering & registration
│   ├── tests/                   # Automated pytest suite
│   ├── requirements.txt         # Backend Python dependencies
│   └── Dockerfile               # Backend container build
│
├── facial-recognition-dashboard/# Next.js Frontend Dashboard
│   ├── app/                     # App router pages & API proxy
│   ├── components/              # Shadcn UI & real-time dashboard tabs
│   ├── lib/                     # API client, TypeScript types, formatters
│   ├── package.json             # Frontend dependencies
│   └── next.config.mjs          # Next.js build configuration
│
├── docker-compose.jarvislabs.yml# Production GPU stack for JarvisLabs
├── Dockerfile.detector          # Dedicated GPU InsightFace detection service container
├── docker-compose.yml           # Local dev multi-container stack
├── DEPLOY_JARVIS_VERCEL.md      # Step-by-step JarvisLabs & Vercel deployment instructions
├── requirements.txt             # Project-wide Python dependencies
└── .env.example                 # Root configuration template
```

---

## Key Components

### 1. Edge CV Node (`facial_recognition/`)
- Captures live video feeds from webcams or RTSP security cameras.
- Uses InsightFace (`buffalo_s` / `buffalo_l`) for face detection, 5-point landmark alignment, and 512-dim embedding extraction.
- Stores local enrollments in `known_faces/gallery.npz`.
- Implements an offline-first cryptographic SQLite WAL ledger (`facial_recognition.db`) guaranteeing zero event loss during network interruptions.
- Streams detection events asynchronously to the cloud with SHA-256 idempotency.

### 2. Cloud API (`backend/`)
- FastAPI server running on JarvisLabs / cloud servers.
- Receives detection events from edge nodes with automatic deduplication.
- Interacts with Supabase PostgreSQL using `pgvector` HNSW indexes for sub-millisecond similarity search.
- Exposes WebSocket channels (`/ws/alerts`, `/ws/kpis`, `/ws/cameras`) for real-time telemetry.
- Provides forensic vector search, duplicate profile identification, and attendance tracking.

### 3. Dashboard (`facial-recognition-dashboard/`)
- Next.js 16 / React application deployed on Vercel.
- Real-time visualization of detections, live camera streams, and critical security alerts.
- Interactive analytics: Footfall charts, camera movement graphs, age/gender demographic slices, and employee attendance.
- Identity management: Enrollment, duplicate profile merging, and unregistered subject labeling.

---

## Data Flow

1. **Local Processing**:
   Camera Frame → Face Detection → Alignment → Embedding → Cosine Comparison against Local Gallery
2. **Local Persistence**:
   Event Transaction Logged to SQLite WAL Ledger (Monotonic Sequence Assigned)
3. **Cloud Synchronization**:
   Async HTTP POST with `event_id` and provenance lineage → Backend API → Supabase PostgreSQL
4. **Real-Time Distribution**:
   Backend triggers WebSocket broadcast → Dashboard updates without browser refresh
