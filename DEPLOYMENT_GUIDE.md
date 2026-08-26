# Deployment Guide — Vercel + Render + Supabase

This project uses three cloud services plus a local edge node:

| Component | Platform | Folder |
|-----------|----------|--------|
| Dashboard | Vercel | `facial-recognition-dashboard/` |
| API | Render | `backend/` |
| Database | Supabase (PostgreSQL + pgvector) | — |
| Edge CV | Your PC | `facial_recognition/` |

No platform change is required for MVP.

---

## 1. Supabase (database)

1. Create a project at [supabase.com](https://supabase.com).
2. Open **SQL Editor** and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Or use `backend/supabase_init.sql`.

3. Copy the **connection string** (Settings → Database → URI).
   - Use the **pooler** URI for Render (`...pooler.supabase.com:5432`).

Tables are created automatically when the backend starts.

---

## 2. Render (backend API)

1. Push this repo to GitHub.
2. Create a **Web Service** on [render.com](https://render.com):
   - Root directory: `backend`
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Python 3.11

3. Set environment variables:

| Variable | Example |
|----------|---------|
| `DATABASE_URL` | `postgresql://postgres....@...pooler.supabase.com:5432/postgres` |
| `CORS_ORIGINS` | `https://your-app.vercel.app,http://localhost:3000` |
| `EDGE_API_KEY` | long random secret (same as edge `.env`) |
| `DEBUG` | `false` |

4. Deploy and test:

```bash
curl https://your-app.onrender.com/health
```

**Note:** Forensic image search (InsightFace) is disabled on Render by default. Edge detection + dashboard analytics still work. Run forensic search against a **local** backend if needed.

---

## 3. Vercel (frontend dashboard)

1. Import the repo on [vercel.com](https://vercel.com).
2. Set **Root Directory** to `facial-recognition-dashboard`.
3. Add environment variables:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://your-app.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://your-app.onrender.com` |

4. Deploy and open your Vercel URL.

5. Go back to Render and add your Vercel URL to `CORS_ORIGINS` if not already there.

---

## 4. Local edge node (webcam)

1. Copy env template:

```powershell
copy .env.example .env
```

2. Edit `.env`:

```env
API_URL=https://your-app.onrender.com
EDGE_API_KEY=same-key-as-render
```

3. Run detection:

```powershell
python facial_recognition\main_cpu.py --max
```

Detections POST to Render → Supabase → dashboard updates via WebSocket.

---

## 5. Sync local gallery to Supabase (one-time)

If you enrolled faces locally but Supabase profiles are empty:

```powershell
python scripts\sync_gallery_to_supabase.py
```

Requires `DATABASE_URL` in `backend/.env`.

---

## 6. Verify end-to-end

- [ ] `GET /health` → `{"status":"ok"}`
- [ ] Run edge camera → Render logs show `POST /api/detections 200`
- [ ] Vercel dashboard → Event trail shows new rows
- [ ] Alerts tab fills for unknown faces
- [ ] WebSocket connected (browser DevTools → Network → WS)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `403 Forbidden` on detections | `EDGE_API_KEY` mismatch between edge `.env` and Render |
| CORS errors in browser | Add exact Vercel URL to Render `CORS_ORIGINS` |
| WebSocket fails | Use `wss://` on Vercel, not `ws://` |
| Empty analytics | Run edge + sync gallery; wait for detections |
| Render cold start (~50s) | Normal on free tier; retry or upgrade to Starter |

---

## Optional upgrades (same stack)

- **Render Starter ($7/mo)** — always-on API, faster WebSocket
- **Supabase Storage** — store face snapshot images later
- **Local backend** — enable forensic search with InsightFace loaded
