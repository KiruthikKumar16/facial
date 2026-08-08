# Multi-Camera Face Detection and Recognition

This repository performs real-time face detection and recognition across a laptop webcam and one or more CCTV cameras accessed via RTSP.

## Features
- Detects and recognizes faces from multiple camera sources simultaneously
- Uses one thread per camera stream to avoid blocking slow or disconnected feeds
- Uses InsightFace SCRFD and ArcFace embeddings for detection and recognition
- Supports CPU and optional GPU inference backends
- Stores enrollments in a serialized gallery and labels detected faces with name + confidence
- Falls back to `Unknown` when no enrolled identity matches the configured threshold
- Logs every detection event to `detections.csv`

## Requirements

- Python 3.10+
- `opencv-python`
- `numpy`
- `PyYAML`
- `insightface`
- `onnxruntime`

Install dependencies:

```bash
pip install -r requirements.txt
```

For GPU inference, install `onnxruntime-gpu` instead of `onnxruntime`:

```bash
pip install onnxruntime-gpu==1.28.0
```

## Quick Start

1. Configure your camera sources in `config.yaml`.
2. Add one folder per person under `known_faces/` with face images.
3. Build the gallery:

```bash
python enroll.py
```

4. Run the standard pipeline:

```bash
python main.py
```

5. Or run the CPU-optimized pipeline:

```bash
python main_cpu.py
```

## Configuration

Edit `config.yaml` to configure cameras and runtime behavior.

Key settings:
- `webcam_index`: local webcam index
- `rtsp_urls`: list of RTSP stream URLs for IP/CCTV cameras
- `similarity_threshold`: cosine similarity threshold for identity matching
- `use_gpu`: set to `true` to use GPU backend with `onnxruntime-gpu`
- `inference_frame_width` / `inference_frame_height`: model input size for inference
- `cpu_inference_frame_width` / `cpu_inference_frame_height`: CPU-optimized model input size
- `cpu_frame_skip`: process every Nth frame on CPU runner
- `cpu_recognition_interval`: recognize faces only every Nth processed frame on CPU runner
- `cpu_use_fast_detector`: use smaller/faster detector model for CPU-only mode
- `cpu_detector_model`: detector model name for CPU-only mode
- `known_faces_dir`: directory containing enrolled identities
- `gallery_path`: saved recognition gallery file
- `log_file`: CSV log path
- `reconnect_interval_seconds`: seconds to wait before retrying a disconnected camera

## Enroll Known Faces

Populate `known_faces/` with one folder per person, and place face images inside each folder:

```text
known_faces/
  Alice/
    alice-1.jpg
    alice-2.jpg
  Bob/
    bob.jpg
```

Then run:

```bash
python enroll.py
```

This builds the gallery file used by the recognition engine.

## Run the Application

For the standard pipeline:

```bash
python main.py
```

For a CPU-optimized runner with frame skipping and tracker fallback:

```bash
python main_cpu.py
```

Press `q` in any display window or use `Ctrl+C` to exit.

## Notes

- If the gallery file is missing or empty, detections are still shown and labeled `Unknown`.
- Each camera runs in its own thread, so one slow stream does not block the others.
- Camera reconnects are retried at the interval configured by `reconnect_interval_seconds`.
- `main_cpu.py` is tuned for CPU-only environments and disables GPU usage.
