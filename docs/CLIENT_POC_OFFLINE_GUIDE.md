# Client POC Guide: Standalone CCTV Audit & Offline Video Ingestion

This guide details how to run the Sentinel Facial Recognition & CCTV Forensics platform **100% standalone and offline** for client demonstrations when receiving **3 days (or any batch) of CCTV video files on an external hard drive**.

---

## 1. Feature Architecture

When a client provides a hard drive of CCTV footage, they prioritize **security and continuity**:
1. **Tamper & Gap Detection**: Audits whether any video clips have been deleted, trimmed, or have time intervals missing.
2. **Cryptographic Chain of Custody**: Computes SHA-256 hashes for all video files.
3. **High-Speed Batch Ingestion**: Processes 72 hours of video at 10x–15x real-time speed using intelligent frame sampling (e.g. 3 FPS) with `cv2.VideoCapture.grab()`.
4. **Accurate Timeline Synchronization**: Binds detected face events, check-ins, and alerts to the **exact recorded timestamps** (not current wall-clock time), populating the 3-day timeline across all dashboard tabs.

---

## 2. Quickstart: 2-Step Client Demonstration

### Option A: Via the Web Dashboard (Recommended for Client Presentation)

1. **Start the Local Backend** (in terminal 1):
   ```bash
   # From repo root
   uvicorn backend.main:app --host 0.0.0.0 --port 1223
   ```
2. **Start the Frontend Dashboard** (in terminal 2):
   ```bash
   cd facial-recognition-dashboard
   npm run dev
   ```
3. Open `http://localhost:3000` in your browser.
4. Click the **"CCTV Audit & Ingest"** tab in the top navigation bar.
5. **Step 1: Run Security & Continuity Audit**:
   - In **Hard Disk CCTV Footage Path**, enter the folder path (e.g., `E:\CCTV_3DAYS` or `D:\footage`).
   - Click **Run Security Audit**.
   - Review:
     - **Security Verdict Banner**: Highlights whether footage is continuous or flags missing time gaps.
     - **Missing Footage Intervals Table**: Shows exact missing intervals (e.g., `2026-10-11 14:10:00 to 14:25:30 (15m 30s)`), preceding/succeeding files, and tamper risk rating (`CRITICAL`, `SUSPICIOUS`).
     - **Chain of Custody Manifest**: Shows per-clip SHA-256 checksums.
     - Click **Export Audit Manifest** to give the client an official JSON/Markdown audit report.
6. **Step 2: Run Batch Face Recognition Ingestion**:
   - Select Sampling Rate (e.g., `3 FPS (Recommended 10x)`).
   - Click **Ingest Face Recognition**.
   - Watch the live progress bar: processed frames, processing speed (FPS), detected faces counter, priority alerts counter, and ETA.
7. **Step 3: Explore Ingested Timeline**:
   - Switch to **Alerts & Event Trail**: View suspect watchlist hits and live feed logs across the 3 days.
   - Switch to **Forensic Search**: Upload a probe photo to track someone's multi-camera path across the 3-day footage.
   - Switch to **Analytics**: View hourly footfall distribution, attendance first-seen/last-seen records, and gender demographics for those dates.

---

### Option B: Via Command Line Interface (CLI)

#### 1. Security & Continuity Audit Only:
```bash
python -m facial_recognition.video_auditor --dir "E:\CCTV_3DAYS" --tolerance 5.0 --output cctv_audit_report.md
```
- Outputs an audit summary to terminal.
- Saves `cctv_audit_report.md` (audit report) and `cctv_audit_report.json`.

#### 2. Batch Video Face Recognition Ingestion:
```bash
python -m facial_recognition.batch_video_ingest --dir "E:\CCTV_3DAYS" --sample-fps 3.0 --threshold 0.60
```
- Ingests all clips sequentially with live terminal progress reporting.
- Writes events directly into the local SQLite database (`facial_recognition.db`).

---

## 3. How Missing Clips and Trimming are Detected

1. **Timestamp Extraction**:
   - Filenames are parsed using regexes for standard NVR naming conventions (Dahua, Hikvision, Uniview, Hanwha, Milestone, ISO 8601, and Unix epoch).
   - If filenames lack timestamps, OS file modification metadata is used.
2. **Interval Calculation**:
   - For consecutive clips $C_i$ and $C_{i+1}$:
     $$\text{Gap} = \text{Start}(C_{i+1}) - \text{End}(C_i)$$
   - If $\text{Gap} > \text{Tolerance}$ (default 5.0s):
     - Flagged as `MISSING_FOOTAGE_GAP`.
     - Classified by severity:
       - **Buffer Hitch** ($< 60\text{s}$): Possible network packet jitter.
       - **Suspicious Cut** ($1\text{m} - 10\text{m}$): Possible trimmed clip or manual camera reboot.
       - **Critical Blackout** ($> 10\text{m}$): Potential security breach, power outage, or intentional deletion.
3. **Abnormal Trim Detection**:
   - If a clip duration is $< 20\%$ of the median clip duration in the dataset (e.g. 45 seconds when standard blocks are 30 minutes), it is flagged as `ABNORMAL_TRIM` (tampered/cut recording).

---

## 4. 100% Offline / Standalone Guarantees

- **No Cloud Dependency**: Runs entirely on local CPU/GPU.
- **Embedded Database**: Defaults to local SQLite (`facial_recognition.db`) with WAL mode enabled.
- **Local AI Models**: Uses InsightFace Buffalo_s models cached in `~/.insightface/models/buffalo_s`.
- **Enrolled Gallery**: Matches against local identities in `known_faces/gallery.npz`.
