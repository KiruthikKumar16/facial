# Facial Recognition Distributed System - Getting Started

This guide explains how to set up and run the distributed facial recognition system with local PC camera, remote Colab/Kaggle detection, and cloud backend.

## System Architecture

The system consists of three main components:

1. **Local PC** (`facial_recognition/pc_frame_sender.py`)
   - Captures video from webcam/RTSP
   - Sends frames to remote detection service
   - Optionally shows local preview with detection results

2. **Remote Detection Service** (Google Colab/Kaggle)
   - `colab_detection_service.py`: FastAPI microservice for face detection/recognition
   - `colab_detection_notebook.ipynb`: Complete Colab notebook for easy deployment
   - Receives frames, runs InsightFace, returns detection results
   - Optionally forwards results to cloud backend

3. **Cloud Backend** (`backend/`)
   - FastAPI server (deployed to Render)
   - Receives detection events
   - Stores in PostgreSQL with pgvector
   - Provides API for dashboard

## Setup Instructions

### Step 1: Set Up Remote Detection Service (Google Colab)

1. Open [Google Colab](https://colab.research.google.com/)
2. Create a new notebook or open `colab_detection_notebook.ipynb`
3. Run all cells in order:

   **Cell 1**: Install required packages
   ```bash
   !pip install insightface onnxruntime-gpu fastapi uvicorn requests opencv-python numpy pyngrok
   ```

   **Cell 2**: Mount Google Drive (optional, for persistent storage)
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   ```

   **Cell 3**: Set up configuration
   ```python
   import os
   os.environ["COLAB_API_KEY"] = "your-secret-key-here"  # Generate a random string
   os.environ["KNOWN_FACES_DIR"] = "/content/known_faces"
   os.environ["GALLERY_PATH"] = "/content/known_faces/gallery.npz"
   os.environ["SIMILARITY_THRESHOLD"] = "0.35"
   # Set CLOUD_BACKEND_URL and CLOUD_API_KEY if you want to forward to cloud
   # os.environ["CLOUD_BACKEND_URL"] = "https://your-backend.onrender.com"
   # os.environ["CLOUD_API_KEY"] = "your-cloud-api-key"
   ```

   **Cell 4**: Prepare known faces gallery
   ```python
   # Upload known faces photos to Colab session
   # Structure: known_faces/person_name/image.jpg
   from facial_recognition.colab_detection_service import compute_gallery_from_directory, save_gallery
   embeddings, labels = compute_gallery_from_directory("/content/known_faces")
   if len(embeddings) > 0:
       save_gallery(embeddings, labels, "/content/known_faces/gallery.npz")
   ```

   **Cell 5**: Initialize the detection service
   ```python
   import uvicorn
   from colab_detection_service import app
   ```

   **Cell 6**: Set up ngrok tunnel
   ```python
   from pyngrok import ngrok
   # Kill any existing tunnels
   ngrok.kill()
   # Create new tunnel
   public_url = ngrok.connect(7860)
   print(" * ngrok tunnel:", public_url)
   print(" * Visit http://127.0.0.1:4040 for ngrok web interface")
   ```

   **Cell 7**: Start the FastAPI server
   ```python
   uvicorn.run(app, host="0.0.0.0", port=7860)
   ```

   **Cell 8**: Test the service (run after server starts)
   ```python
   import requests
   import json
   health_response = requests.get(f"{public_url}/health")
   print("Health check:", health_response.json())
   ```

4. **Important**: Copy the ngrok public URL from Cell 8 output (looks like `https://xxxxxxxx.ngrok.io`)
5. **Important**: Note your `COLAB_API_KEY` from Cell 3

### Step 2: Configure Local PC Frame Sender

1. Edit `facial_recognition/pc_frame_sender.py`:
   ```python
   REMOTE_URL = "https://your-colab-tunnel.ngrok.io"  # From Colab Cell 8
   API_KEY = "your-secret-key-here"  # From Colab Cell 3
   ```

2. Optional adjustments:
   - `camera_source`: "webcam" or "rtsp"
   - `webcam_index`: Usually 0 for default webcam
   - `fps`: Frame rate to send (5-10 recommended for Colab)
   - `show_preview`: Set to False to disable local preview window

### Step 3: Run the System

1. **Start the Colab detection service** (keep the notebook running with all cells executed, especially the server in Cell 7)

2. **Run the PC frame sender**:
   ```bash
   cd facial_recognition
   python pc_frame_sender.py
   ```

3. **Verify operation**:
   - You should see a preview window with detection boxes and labels
   - Green boxes = recognized faces, Red boxes = unknown faces
   - Console output shows statistics periodically
   - In Colab, you should see detection requests in the server logs

### Step 4: Optional - Forward to Cloud Backend

If you want to also send detections to your cloud backend:

1. In Colab notebook Cell 3, uncomment and set:
   ```python
   os.environ["CLOUD_BACKEND_URL"] = "https://your-backend.onrender.com"
   os.environ["CLOUD_API_KEY"] = "your-cloud-api-key-from-backend-env"
   ```

2. Restart the Colab service (stop and rerun the server cell)

### Troubleshooting

#### Common Issues:

1. **"Connection refused" errors**:
   - Make sure Colab server is running (Cell 7 executing)
   - Verify ngrok tunnel is active (check Cell 8 output)
   - Check that REMOTE_URL matches the ngrok URL exactly

2. **API key errors**:
   - Ensure `COLAB_API_KEY` in Colab matches `API_KEY` in pc_frame_sender.py
   - No extra spaces or quotes in either value

3. **No detections showing**:
   - Check if known faces gallery is loaded properly in Colab
   - Verify similarity threshold (0.35 is good starting point)
   - Make sure faces are well-lit and frontal in the camera view

4. **Performance issues**:
   - Lower FPS in pc_frame_sender.py (try 3-5)
   - Ensure Colab is using GPU (Runtime → Change runtime type → GPU)
   - Reduce frame width/height if needed (640x640 is recommended)

### Directory Structure Overview

```
facial/
├── facial_recognition/
│   ├── data/                 # Moved CSV detection logs
│   ├── known_faces/          # Known faces gallery (organized by person)
│   ├── pending/              # Temporary storage for unknown faces
│   ├── pc_frame_sender.py    # PC → Remote frame sender
│   ├── main.py               # Local processing (GPU)
│   ├── main_cpu.py           # Local processing (CPU)
│   └── ...                   # Other modules
├── colab_detection_service.py   # Colab detection microservice
├── colab_detection_notebook.ipynb # Colab notebook for remote detection
├── backend/                  # Cloud API (FastAPI)
├── facial-recognition-dashboard/ # Next.js frontend
└── scripts/                  # PowerShell helper scripts
```

### Next Steps

1. **Enroll new known faces**:
   - Add person folders to `known_faces/` directory
   - Run `python facial_recognition/enroll.py` to rebuild gallery
   - Or upload new faces to Colab known_faces directory and recompute gallery

2. **Review unknown faces**:
   - Run `python facial_recognition/review_pending.py`
   - Label unknown faces to add them to known gallery

3. **View analytics**:
   - Access your cloud dashboard at the frontend URL
   - See real-time detections, analytics, and forensic search

4. **Scale the system**:
   - Add multiple PC frame senders for different cameras
   - Use different Colab instances for parallel processing
   - Configure camera routes in config.yaml for multi-camera tracking

---

**Note**: Keep the Colab notebook running with the server active while using the system. If you disconnect from Colab, you'll need to restart the tunnel and server.