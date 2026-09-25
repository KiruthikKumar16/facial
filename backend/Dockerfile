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

COPY backend/ ./backend/
COPY facial_recognition/ ./facial_recognition/

ENV PYTHONPATH=/app/backend:/app

EXPOSE 1223

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "1223"]
