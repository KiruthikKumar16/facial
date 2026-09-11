"""
Google Colab/Kaggle Face Detection Service
Runs a FastAPI microservice that receives frames, performs face detection/recognition,
and optionally forwards results to a cloud backend.
"""
import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis
from fastapi import FastAPI, File, UploadFile, HTTPException, Header
from fastapi.responses import JSONResponse
import uvicorn
import os
from typing import Optional, List, Dict, Any
import logging
from pathlib import Path
import json
import numpy as np
import requests
from datetime import datetime, timezone
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Remote Face Detection Service")

# Global variables for models and gallery
detector_app: Optional[FaceAnalysis] = None
known_gallery_embeddings: Optional[np.ndarray] = None
known_gallery_labels: Optional[List[str]] = None
similarity_threshold: float = 0.35
cloud_backend_url: Optional[str] = None
cloud_api_key: Optional[str] = None

# Detection result template matching the format expected by backend/main.py
def create_detection_template() -> Dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "embedding": [],  # Will be filled with 512-dim vector
        "device_id": "local_pc",  # Could be made configurable
        "sequence_number": 0,  # Will be incremented per detection
        "camera_id": "webcam",  # Could be made configurable
        "profile_id": None,  # Will be set if recognized
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "unknown",  # Will be set based on recognition
        "confidence": 0.0,
        "bbox": [0, 0, 0, 0],  # [x0, y0, x1, y1]
        "liveness_score": 0.0,
        "age": 0,
        "gender": "unknown",
        "wearing_mask": False,
        "wearing_glasses": False,
        "priority": "normal",
        "config_version": 1,
        "detection_model_version": "scrfd_500m_bnkps_v1",
        "embedding_model_version": "w600k_mbf_v1",
        "gallery_version": 1,
        "threshold_version": 1,
        "camera_config_version": 1,
        "algorithm_version": "temporal_fusion_v2",
        "version_bundle_hash": ""  # Will be computed
    }

@app.on_event("startup")
async def startup_event():
    """Initialize models and load known faces gallery on startup."""
    global detector_app, known_gallery_embeddings, known_gallery_labels
    global similarity_threshold, cloud_backend_url, cloud_api_key

    logger.info("Starting up face detection service...")

    # Load configuration from environment variables
    similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.35"))
    cloud_backend_url = os.getenv("CLOUD_BACKEND_URL")
    cloud_api_key = os.getenv("CLOUD_API_KEY")

    if cloud_backend_url:
        logger.info(f"Will forward detections to cloud backend: {cloud_backend_url}")
    else:
        logger.warning("No cloud backend URL configured - detections will not be forwarded")

    # Initialize InsightFace detector
    logger.info("Loading InsightFace model...")
    try:
        # Use GPU if available, otherwise CPU
        ctx_id = 0 if os.getenv("USE_GPU", "false").lower() == "true" else -1
        detector_app = FaceAnalysis(name='buffalo_s', providers=['CUDAExecutionProvider'] if ctx_id == 0 else ['CPUExecutionProvider'])
        detector_app.prepare(ctx_id=ctx_id, det_size=(640, 640))
        logger.info(f"InsightFace model loaded successfully (ctx_id: {ctx_id})")
    except Exception as e:
        logger.error(f"Failed to load InsightFace model: {e}")
        raise

    # Load known faces gallery
    logger.info("Loading known faces gallery...")
    gallery_path = os.getenv("GALLERY_PATH", "known_faces/gallery.npz")
    known_faces_dir = os.getenv("KNOWN_FACES_DIR", "known_faces")

    try:
        # Try to load precomputed gallery first
        if os.path.exists(gallery_path):
            logger.info(f"Loading gallery from {gallery_path}")
            data = np.load(gallery_path, allow_pickle=True)
            known_gallery_labels = list(data['labels'])
            known_gallery_embeddings = np.asarray(data['embeddings'])
            logger.info(f"Loaded gallery with {len(known_gallery_labels)} identities")
        else:
            # Compute gallery from known_faces directory
            logger.info(f"Computing gallery from directory: {known_faces_dir}")
            known_gallery_embeddings, known_gallery_labels = compute_gallery_from_directory(known_faces_dir)
            # Optionally save the computed gallery
            if known_gallery_embeddings is not None and len(known_gallery_embeddings) > 0:
                save_path = Path(gallery_path)
                save_path.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(save_path,
                                  labels=np.array(known_gallery_labels, dtype=object),
                                  embeddings=known_gallery_embeddings)
                logger.info(f"Saved computed gallery to {gallery_path}")
    except Exception as e:
        logger.error(f"Failed to load known faces gallery: {e}")
        # Continue with empty gallery - will treat all faces as unknown
        known_gallery_embeddings = np.zeros((0, 512), dtype=np.float32)
        known_gallery_labels = []

def compute_gallery_from_directory(known_faces_dir: str) -> tuple[np.ndarray, List[str]]:
    """Compute face embeddings from images in known_faces directory structure."""
    embeddings = []
    labels = []

    known_faces_path = Path(known_faces_dir)
    if not known_faces_path.exists():
        logger.warning(f"Known faces directory not found: {known_faces_dir}")
        return np.zeros((0, 512), dtype=np.float32), []

    logger.info(f"Scanning {known_faces_dir} for known faces...")
    for person_dir in known_faces_path.iterdir():
        if not person_dir.is_dir():
            continue

        person_name = person_dir.name
        person_embeddings = []

        # Process all images in the person's directory
        for img_path in person_dir.glob("*.[jp][pn]g"):  # jpg, jpeg, png
            try:
                img = cv2.imread(str(img_path))
                if img is None:
                    logger.warning(f"Could not read image: {img_path}")
                    continue

                # Detect faces
                faces = detector_app.get(img)
                if not faces:
                    logger.warning(f"No face detected in: {img_path}")
                    continue

                # Use the largest face (by bounding box area)
                largest_face = max(faces, key=lambda f:
                                 (f['bbox'][2] - f['bbox'][0]) * (f['bbox'][3] - f['bbox'][1]))
                embedding = largest_face.embedding

                if embedding is not None and len(embedding) == 512:
                    person_embeddings.append(embedding)
                    logger.debug(f"Added embedding for {person_name} from {img_path.name}")
                else:
                    logger.warning(f"Invalid embedding for {img_path}")

            except Exception as e:
                logger.error(f"Error processing {img_path}: {e}")

        if person_embeddings:
            # Average embeddings for this person
            avg_embedding = np.mean(person_embeddings, axis=0)
            # Normalize
            avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)
            embeddings.append(avg_embedding)
            labels.append(person_name)
            logger.info(f"Added {person_name} with {len(person_embeddings)} images")
        else:
            logger.warning(f"No valid embeddings found for {person_name}")

    if len(embeddings) == 0:
        logger.warning("No known faces found - gallery will be empty")
        return np.zeros((0, 512), dtype=np.float32), []

    return np.asarray(embeddings, dtype=np.float32), labels

def recognize_face(embedding: np.ndarray) -> tuple[Optional[str], float]:
    """
    Recognize a face by comparing against the known gallery.
    Returns (identity, confidence) where identity is None if unknown.
    """
    if known_gallery_embeddings is None or len(known_gallery_embeddings) == 0:
        return None, 0.0

    # Normalize the query embedding
    query_norm = embedding / np.linalg.norm(embedding)

    # Compute cosine similarity with all known embeddings
    # known_gallery_embeddings should already be normalized
    similarities = np.dot(known_gallery_embeddings, query_norm)

    # Find the best match
    best_idx = np.argmax(similarities)
    best_similarity = similarities[best_idx]

    if best_similarity >= similarity_threshold:
        return known_gallery_labels[best_idx], float(best_similarity)
    else:
        return None, float(best_similarity)

@app.post("/detect")
async def detect_faces(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    Detect faces in an uploaded image and return detection results.

    Expected format matches what the cloud backend's /api/detections expects.
    """
    global detector_app, known_gallery_embeddings, known_gallery_labels
    global similarity_threshold, cloud_backend_url, cloud_api_key

    # Optional API key validation
    expected_api_key = os.getenv("COLAB_API_KEY")  # Different from edge API key
    if expected_api_key and x_api_key != expected_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if detector_app is None:
        raise HTTPException(status_code=503, detail="Detection service not initialized")

    try:
        # Read and decode the image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image format")

        # Run face detection
        faces = detector_app.get(img)

        detections = []
        sequence_offset = 0  # In a real system, this would be maintained per camera

        for i, face in enumerate(faces):
            # Extract bounding box and embedding
            bbox = face['bbox'].astype(int)  # [x0, y0, x1, y1]
            embedding = face.embedding

            if embedding is None or len(embedding) != 512:
                logger.warning(f"Skipping face {i} due to invalid embedding")
                continue

            # Recognize the face
            identity, confidence = recognize_face(embedding)

            # Create detection record
            detection = create_detection_template()
            detection["event_id"] = str(uuid.uuid4())
            detection["embedding"] = embedding.tolist()
            detection["device_id"] = "local_pc"  # Could extract from headers or make configurable
            detection["sequence_number"] = sequence_offset + i
            detection["camera_id"] = "webcam"  # Could extract from headers or make configurable
            detection["timestamp"] = datetime.now(timezone.utc).isoformat()
            detection["confidence"] = confidence
            detection["bbox"] = [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]

            if identity is not None:
                # Recognized face
                detection["identity"] = identity
                detection["status"] = "recognized"
                # Look up profile_id if needed (would need database lookup in real implementation)
                # For now, we'll leave profile_id as None and let backend handle it
                # In a full implementation, you'd query the cloud backend for the profile
            else:
                # Unknown face
                detection["identity"] = "Unknown"
                detection["status"] = "unknown"
                # Generate a temporary label for unknown faces
                detection["identity"] = f"Person {hash(str(embedding.tobytes())) % 10000}"

            # Extract additional attributes if available from the model
            # Note: InsightFace buffalo_s model provides age and gender
            if hasattr(face, 'age') and face.age is not None:
                detection["age"] = int(face.age)
            if hasattr(face, 'gender') and face.gender is not None:
                detection["gender"] = "male" if face.gender == 1 else "female"

            detections.append(detection)

        # Optionally forward detections to cloud backend
        if cloud_backend_url and cloud_api_key and detections:
            forwarded_count = 0
            for detection in detections:
                try:
                    # Prepare headers for cloud backend
                    headers = {
                        "X-API-Key": cloud_api_key,
                        "Content-Type": "application/json"
                    }

                    # Send to cloud backend
                    response = requests.post(
                        f"{cloud_backend_url}/api/detections",
                        json=detection,
                        headers=headers,
                        timeout=5
                    )

                    if response.status_code == 200:
                        forwarded_count += 1
                    else:
                        logger.warning(f"Failed to forward detection to cloud: {response.status_code}")

                except Exception as e:
                    logger.error(f"Error forwarding detection to cloud: {e}")

            logger.info(f"Forwarded {forwarded_count}/{len(detections)} detections to cloud backend")

        # Return detection results
        return JSONResponse(content={
            "detections": detections,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "frame_shape": list(img.shape) if img is not None else [0, 0, 0]
        })

    except Exception as e:
        logger.error(f"Error in detect_faces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy" if detector_app is not None else "initializing",
        "model_loaded": detector_app is not None,
        "gallery_size": len(known_gallery_labels) if known_gallery_labels else 0,
        "similarity_threshold": similarity_threshold,
        "cloud_backend_configured": cloud_backend_url is not None
    }

if __name__ == "__main__":
    # For running directly (not recommended in Colab - use uvicorn programmatically)
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")