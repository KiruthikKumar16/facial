"""Local forensic search proxy for cloud dashboards.

The dashboard sends probe images here, on the edge machine. This service
extracts the face embedding locally with InsightFace, then sends only the
512-dimensional vector to the cloud backend for pgvector search.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

import cv2
import numpy as np
import requests
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:
    from .detector import InsightFaceDetector
except ImportError:  # Allows: python facial_recognition/forensic_edge.py
    sys.path.append(str(Path(__file__).resolve().parent))
    from detector import InsightFaceDetector  # type: ignore


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

app = FastAPI(title="Facial Recognition Edge Forensic Proxy")
_detector: Optional[InsightFaceDetector] = None
_detector_lock = Lock()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _load_config() -> dict:
    config_path = Path(__file__).resolve().parent / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("Could not load config.yaml: %s", exc)
        return {}


def _cors_origins() -> list[str]:
    raw = os.environ.get("EDGE_FORENSIC_CORS_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


def get_detector() -> InsightFaceDetector:
    global _detector
    if _detector is not None:
        return _detector

    with _detector_lock:
        if _detector is not None:
            return _detector

        cfg = _load_config()
        use_gpu = _bool_env("EDGE_FORENSIC_USE_GPU", bool(cfg.get("use_gpu", False)))
        det_w = _int_env("EDGE_FORENSIC_DET_WIDTH", int(cfg.get("inference_frame_width", 640)))
        det_h = _int_env("EDGE_FORENSIC_DET_HEIGHT", int(cfg.get("inference_frame_height", 640)))
        model_name = os.environ.get("EDGE_FORENSIC_MODEL", str(cfg.get("cpu_detector_model", "buffalo_s")))
        fast_detector = _bool_env("EDGE_FORENSIC_FAST_DETECTOR", bool(cfg.get("cpu_use_fast_detector", False)))

        logger.info(
            "Loading edge forensic model %s on %s with det_size=(%d, %d)",
            model_name,
            "GPU" if use_gpu else "CPU",
            det_w,
            det_h,
        )
        _detector = InsightFaceDetector(
            use_gpu=use_gpu,
            det_size=(det_w, det_h),
            model_name=model_name,
            fast_detector=fast_detector,
        )
        return _detector


async def extract_embedding(image: UploadFile) -> list[float]:
    contents = await image.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=422, detail="Uploaded file is not a readable image.")

    detector = get_detector()
    faces = detector.detect(frame)
    if not faces:
        raise HTTPException(status_code=422, detail="No face was detected in the uploaded image.")

    face = max(
        faces,
        key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]),
    )
    embedding = detector.extract_embedding(frame, face)
    if embedding is None:
        raise HTTPException(status_code=422, detail="Could not extract a face embedding.")

    return np.asarray(embedding, dtype=np.float32).flatten().tolist()


def _parse_camera_ids(camera_ids: Optional[str]) -> list[str]:
    return [camera_id.strip() for camera_id in (camera_ids or "").split(",") if camera_id.strip()]


def _iso_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": _detector is not None,
        "cloud_api_url": os.environ.get("API_URL", "").rstrip("/"),
    }


@app.post("/api/forensic/search")
async def search(
    image: UploadFile = File(...),
    threshold: float = Form(0.60),
    date_from: Optional[datetime] = Form(None),
    date_to: Optional[datetime] = Form(None),
    camera_ids: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    age_min: Optional[int] = Form(None),
    age_max: Optional[int] = Form(None),
    wearing_mask: Optional[bool] = Form(None),
    wearing_glasses: Optional[bool] = Form(None),
) -> list[dict]:
    api_url = os.environ.get("API_URL", "").rstrip("/")
    api_key = os.environ.get("EDGE_API_KEY", "")
    if not api_url:
        raise HTTPException(status_code=500, detail="Set API_URL to your Render backend URL.")
    if not api_key:
        raise HTTPException(status_code=500, detail="Set EDGE_API_KEY to match the Render backend.")

    embedding = await extract_embedding(image)
    payload = {
        "embedding": embedding,
        "threshold": threshold,
        "date_from": _iso_datetime(date_from),
        "date_to": _iso_datetime(date_to),
        "camera_ids": _parse_camera_ids(camera_ids),
        "gender": gender,
        "age_min": age_min,
        "age_max": age_max,
        "wearing_mask": wearing_mask,
        "wearing_glasses": wearing_glasses,
    }

    try:
        response = requests.post(
            f"{api_url}/api/internal/forensic/search-vector",
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach cloud backend: {exc}") from exc

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response.json()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("EDGE_FORENSIC_HOST", "127.0.0.1")
    port = _int_env("EDGE_FORENSIC_PORT", 8765)
    uvicorn.run("facial_recognition.forensic_edge:app", host=host, port=port)
