# Facial Recognition & Analytics Platform - Project Overview

## Directory Structure

```
facial/
├── facial_recognition/          # Edge CV Node (local processing)
│   ├── data/                    # CSV detection logs (migrated from root)
│   ├── known_faces/             # Known faces gallery (organized by person)
│   ├── pending/                 # Temporary storage for unknown faces
│   ├── main.py                  # Main entry point (GPU optimized)
│   ├── main_cpu.py              # CPU-optimized version
│   ├── pc_frame_sender.py       # PC frame sender for remote detection
│   ├── remote_detector.py       # Remote detection client
│   ├── enroll.py                # Build gallery from known_faces/
│   ├── review_pending.py        # Review and label unknown faces
│   ├── detector.py              # Face detection wrapper
│   ├── recognizer.py            # Face recognition logic
│   ├── logger.py                # Detection logging and cloud sync
│   ├── event_ledger.py          # Transactional event ledger (SQLite)
│   ├── config.yaml              # Configuration file
│   └── ...                      # Other modules (tracking, quality, etc.)
│
├── backend/                     # Cloud API (FastAPI)
│   ├── main.py                  # FastAPI application entry point
│   ├── models.py                # SQLAlchemy models
│   ├── schemas.py               # Pydantic schemas
│   ├── config.py                # Configuration
│   ├── database.py              # Database setup
│   ├── websocket.py             # WebSocket handlers
│   └── ...                      # Routers, tasks, etc.
│
├── facial-recognition-dashboard/# Next.js frontend dashboard
│   ├── ...                      # Next.js application
│
├── scripts/                     # PowerShell helper scripts
│   ├── setup-all.ps1            # Complete setup
│   ├── run-backend.ps1          # Start backend
│   ├── run-frontend.ps1         # Start frontend
│   ├── DEPLOYMENT_CHECKLIST.ps1 # Validate environment
│   └── sync_gallery_to_supabase.py # Sync gallery to cloud
│
├── colab_detection_service.py   # Google Colab detection service
├── colab_detection_notebook.ipynb # Colab notebook for remote detection
├── docker-compose.yml           # Docker compose configuration
├── README.md                    # This file
└── requirements.txt             # Python dependencies
```

## Key Components

### 1. Edge CV Node (`facial_recognition/`)
- Processes live video feeds locally
- Uses InsightFace/ONNX for face detection and recognition
- Maintains local known faces gallery (`known_faces/`)
- Logs detections to SQLite ledger (`facial_recognition.db`)
- Synchronizes with cloud via dual-write pipeline (local CSV + async POST)
- Handles unknown face review and enrollment

### 2. Cloud API (`backend/`)
- FastAPI server running on Render
- Receives detection events from edge nodes
- Stores events in PostgreSQL with pgvector extension
- Provides REST API for dashboard and mobile clients
- Handles WebSocket connections for real-time updates
- Includes forensic search, analytics, and management endpoints

### 3. Dashboard (`facial-recognition-dashboard/`)
- Next.js 14 React application
- Real-time visualization of detections, alerts, and analytics
- WebSocket connections for live updates
- Forensic search interface
- Identity management and deduplication tools

### 4. Remote Detection (Colab/Kaggle)
- `colab_detection_service.py`: Detection microservice for Colab
- `colab_detection_notebook.ipynb`: Ready-to-use Colab notebook
- `pc_frame_sender.py`: Sends frames from PC to Colab for processing
- Enables offloading heavy ML inference to cloud GPUs

## Data Flow

1. **Local Processing**: 
   - Camera → Face Detection → Recognition → Local Storage (SQLite + CSV)
   
2. **Cloud Synchronization**:
   - Local events → Async POST → Cloud API → PostgreSQL
   
3. **Dashboard Updates**:
   - Cloud DB → REST/WebSocket → Frontend UI
   
4. **Remote Detection (Optional)**:
   - PC Camera → Frame Sender → Colab Detection → Results → Cloud API

## Getting Started

See `scripts/setup-all.ps1` for complete automated setup, or follow these steps:

1. **Database**: Set up Supabase PostgreSQL with pgvector extension
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
   python run.py          # GPU
   # or
   python main_cpu.py     # CPU optimized
   ```

## Configuration

Key configuration files:
- `facial_recognition/config.yaml` - Edge node settings
- `backend/config.py` - Backend settings
- Environment variables (see `.env.example`)

## Features

- Real-time face detection and recognition
- PostgreSQL pgvector for similarity search
- Dual-write pipeline for zero data loss
- Identity deduplication
- Cross-camera tracking
- Forensic search capabilities
- WebSocket-based real-time dashboard
- Configurable quality thresholds
- Remote detection via Colab/Kaggle
- Comprehensive analytics and reporting

