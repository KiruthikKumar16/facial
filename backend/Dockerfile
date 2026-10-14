FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV and builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download InsightFace buffalo_s model into image layer
# so container boots instantly without cold-start download / healthcheck timeout
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_s').prepare(ctx_id=-1, det_size=(320, 320))"

COPY backend/ ./backend/
COPY facial_recognition/ ./facial_recognition/

ENV PYTHONPATH=/app/backend:/app

EXPOSE 1223

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "1223", "--proxy-headers", "--forwarded-allow-ips=*"]
