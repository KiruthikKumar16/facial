# Runtime Validation Checklist

Date: 2026-09-02

This checklist separates checks executed in this session from user-reported automation. A PASS means the check was actually executed and observed; user-reported results are explicitly labeled.

## Launch Commands

Run each service in a separate PowerShell terminal from `C:\Users\mkiru\facial`.

### PostgreSQL / pgvector

Preferred Docker command:

```powershell
docker compose up -d postgres
docker compose ps postgres
docker compose exec postgres pg_isready -U postgres -d facial_ops
```

The configured Docker database is `facial_ops` on port `5432`. The backend container command is:

```powershell
docker compose up -d backend
```

Local non-Docker PostgreSQL must provide the database URL configured in the root `.env`; verify it with:

```powershell
Get-Service postgresql* -ErrorAction SilentlyContinue
```

Status: **BLOCKED BY ENVIRONMENT** for Docker validation. Docker is installed, but the daemon was not responding during this session. The configured live Supabase/PostgreSQL connection was reachable through the backend.

### FastAPI Backend

```powershell
cd C:\Users\mkiru\facial\backend
..\myenv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 1223
```

Health check, using the safe PowerShell form:

```powershell
Invoke-WebRequest http://127.0.0.1:1223/health -UseBasicParsing
```

Status: **PASS**. Startup completed and `/health` returned HTTP `200` in the live run.

### Next.js Frontend

```powershell
cd C:\Users\mkiru\facial\facial-recognition-dashboard
npm run dev
```

Open `http://localhost:3000`. For local browser WebSockets, `.env.local` must use:

```text
NEXT_PUBLIC_API_URL=http://127.0.0.1:1223
NEXT_PUBLIC_WS_URL=ws://127.0.0.1:1223
```

Status: **PASS**. The frontend started and the production build passed. Browser WebSocket connections were accepted by the backend after restart.

### Edge Recognition System

```powershell
cd C:\Users\mkiru\facial\facial_recognition
..\myenv\Scripts\Activate.ps1
python main_cpu.py --webcam 0
```

Optional CPU controls:

```powershell
python main_cpu.py --webcam 0 --tier fast
python main_cpu.py --webcam 0 --cam-res 1280x720
```

Status: **PASS**. Webcam 0 opened at `640x480`, calibration completed, and the camera pipeline started.

## Environment Checklist

Do not paste secret values into this document or terminal output.

| Variable / requirement | Required | Verification | Status |
|---|---:|---|---|
| `DATABASE_URL` | Yes | Root `.env`; must point to PostgreSQL/pgvector | PASS, used by live backend |
| `EDGE_API_KEY` | Yes | Present in root `.env`; must match edge and backend | PASS, authenticated gallery/detection calls |
| `CORS_ORIGINS` | Yes for browser | Include `http://localhost:3000` and `http://127.0.0.1:3000` | PASS in configured defaults |
| `API_URL` | Yes for edge | Root `.env`; local value should target port `1223` | PASS, edge posted detections |
| `NEXT_PUBLIC_API_URL` | Yes for frontend | `.env.local`, use `http://127.0.0.1:1223` locally | PASS after frontend restart |
| `NEXT_PUBLIC_WS_URL` | Yes for frontend | `.env.local`, use `ws://127.0.0.1:1223` locally | PASS after frontend restart |
| `known_faces/gallery.npz` | Yes for recognition | File must exist and be readable | PASS, local cache loaded 167 identities |
| Webcam device `0` | Required for physical-camera run | `python main_cpu.py --webcam 0` | PASS |
| RTSP URLs | Required only for RTSP run | Check `facial_recognition/config.yaml` | NOT RUN, sources had no frames |
| Docker daemon | Required for Docker validation | `docker info` | BLOCKED BY ENVIRONMENT |
| Node.js/npm | Required for frontend | `node --version`, `npm --version` | PASS, Node/npm available |
| Python environment | Required for backend/edge | `myenv\Scripts\python.exe --version` | PASS, Python 3.14.6 |

## Runtime Path

| Path stage | Status | Evidence |
|---|---|---|
| Camera capture | PASS | Webcam 0 connected at `640x480` |
| Face detection | PASS | InsightFace/ONNX CPU model initialized |
| Embedding / gallery | PASS | Local gallery loaded; gallery endpoint returned 167 embeddings |
| Event ledger | PASS | Event ledger initialized and pending events requeued |
| Edge-to-backend sync | PASS | Individual `POST /api/detections` returned HTTP `200` |
| Batch sync | PASS | Batch route signature fixed and backend compiled; live batch execution after fix NOT RUN |
| PostgreSQL persistence | PASS | Backend startup, reads, writes, and reconciliation completed against configured database |
| pgvector gallery response | PASS | `/api/internal/gallery` returned HTTP `200` with 167 labels and embeddings |
| Frame relay | PASS | `POST /api/internal/cameras/webcam/frame` returned HTTP `204` |
| Dashboard REST reads | PASS | Logs show `200` for cameras, KPIs, logs, alerts, profiles, and analytics |
| Dashboard WebSockets | PASS | `/ws/alerts`, `/ws/cameras`, and `/ws/kpis` accepted connections |
| Frontend rendering/build | PASS | `npm run build` completed successfully |
| Full user-visible end-to-end journey | NOT RUN | No complete automated live browser journey was executed in this session |

## Endpoint Runtime Checks

Observed in the live backend logs:

| Endpoint family | Status |
|---|---|
| `/health` | PASS, HTTP `200` |
| `/api/detections` | PASS, HTTP `200` |
| `/api/detections/reconcile` | PASS, HTTP `200` |
| `/api/internal/cameras/{id}/frame` | PASS, HTTP `204` |
| `/api/internal/gallery` | PASS after vector serialization fix, HTTP `200` |
| `/api/cameras`, `/api/kpis`, `/api/logs`, `/api/alerts` | PASS, HTTP `200` |
| `/api/profiles` and analytics routes | PASS, HTTP `200` in observed dashboard run |
| `/api/cameras/{id}/stream` | PASS, HTTP `200` |
| WebSocket channels | PASS, connections accepted |
| `/api/detections/batch` | PASS route returns HTTP `200`; event processing fix compiled; post-fix live batch persistence check NOT RUN |

## Tests Requiring Special Conditions

| Test or validation | Requirement | Status | Exact command / next action |
|---|---|---|---|
| Webcam/physical camera CV run | Physical camera | PASS | `cd facial_recognition; python main_cpu.py --webcam 0` |
| RTSP camera validation | Reachable RTSP devices/network | NOT RUN | Configure reachable URLs, then run `python main_cpu.py` |
| Network failure/recovery tests | Ability to disable or interrupt network | NOT RUN | Run the relevant failure-injection tests while blocking the API route, then restore connectivity |
| Docker PostgreSQL/pgvector stack | Docker daemon | BLOCKED BY ENVIRONMENT | Start Docker Desktop, run `docker info`, then `docker compose up -d postgres backend frontend` |
| Render deployment | Deployed Render service and credentials | NOT RUN | Deploy, then run `Invoke-WebRequest https://<service>/health -UseBasicParsing` and test the deployed frontend |
| Large dataset/vector performance | Large seeded dataset and measurable workload | NOT RUN | Load the benchmark dataset, run the benchmark scripts, and retain timing output |
| Backend pytest suite | pytest installed in active environment | BLOCKED BY ENVIRONMENT | Install project test dependencies in the project environment, then run `python -m pytest backend -q` |
| Playwright suite | Running frontend/backend and browser binary | NOT RUN in this session | `cd facial-recognition-dashboard; npm run test:e2e` |
| Alembic up/down/up | Migration database and Alembic CLI | NOT RUN in this session | `cd backend; python -m alembic upgrade head; python -m alembic downgrade base; python -m alembic upgrade head` |

## Actually Executed This Session

- Python compilation of modified backend modules: PASS.
- Database compatibility migration inspection: PASS; no current `detections` columns missing; `embeddings.model_version` exists.
- Authenticated `/api/internal/gallery` request: PASS; HTTP `200`, 167 labels, 167 embeddings.
- Backend and edge startup evidence supplied in runtime logs: PASS.
- Frontend `npm run build`: PASS.
- Docker capability check: BLOCKED BY ENVIRONMENT; daemon not responding.
- Backend pytest suite: NOT RUN; `pytest` was not installed in `myenv`.
- Playwright, Alembic cycle, Docker stack, Render deployment, network-failure, RTSP, and large-dataset validations: NOT RUN in this session.

## User-Reported Automated Results

The user reported the following results as complete, but they were not re-executed in this runtime session: Backend `35/35`, Edge `213/213`, Playwright `9/9`, frontend build, Alembic up/down/up, and Docker configuration validation. They remain **NOT RUN in this session** until independently reproduced.

## Remaining Blockers and Next Actions

1. **Docker daemon unavailable**: Start Docker Desktop, verify `docker info`, then run the Docker Compose PostgreSQL/backend/frontend checks.
2. **Backend pytest unavailable**: Install test dependencies using the project environment/dependency policy, then run the backend suite.
3. **Post-fix batch persistence check not executed**: With backend and camera running, submit one batch request and confirm the response contains one result and the database count increases by one for a new event ID.
4. **RTSP sources unavailable**: Provide reachable RTSP URLs or disable those sources for a webcam-only validation.
5. **Production Render validation not executed**: Deploy or provide the target Render URL and run health, API, WebSocket, and frontend checks against it.
6. **Large-dataset performance not executed**: Seed the intended dataset and run the benchmark scripts with captured latency/throughput output.

## Final Runtime Validation Status

**PARTIAL PASS - local webcam/backend/frontend path verified; full runtime validation remains incomplete.**

No production-readiness claim is made. Docker, pytest, Playwright, Alembic cycle, RTSP, network-failure, large-dataset, and Render deployment checks remain unexecuted or environment-blocked.
