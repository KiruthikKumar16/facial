# ⚡ QUICK COMMAND REFERENCE

Copy-paste these commands in the order shown.

---

## PHASE 0: Push to GitHub

```powershell
# Navigate to project
cd c:\Users\mkiru\facial

# Initialize git
git init

# Stage all files
git add .

# Commit
git commit -m "Initial commit: facial recognition system"

# Rename branch to main
git branch -M main

# Add your GitHub repo (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/facial.git

# Push to GitHub
git push -u origin main

# Verify (you should see all files on GitHub)
```

---

## PHASE 1: Supabase Setup (Do in Web Browser)

```
1. Go to: https://supabase.com
2. Click "Sign Up"
3. Use GitHub or email
4. Create new project:
   - Name: facial-recognition
   - Region: closest to you
   - Postgres Version: 15
5. Wait 2-3 minutes
6. Go to Settings → Database
7. Copy Connection String (URI format)
8. Go to SQL Editor
9. Run: CREATE EXTENSION IF NOT EXISTS vector;
10. Paste and run ALL the SQL from COMPLETE_DEPLOYMENT_STEPS.md Step 1.5
11. ✅ SAVE YOUR CONNECTION STRING!
```

---

## PHASE 2A: Test Backend Locally (Optional)

```powershell
# Set Supabase connection string
$env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@db.YOUR_REGION.supabase.co:5432/postgres"

# Navigate to backend
cd c:\Users\mkiru\facial\backend

# Start backend
python main.py

# In browser, visit:
# http://localhost:8000/docs

# Stop with: Ctrl+C
```

---

## PHASE 2B: Deploy Backend to Render (Do in Web Browser)

```
1. Go to: https://render.com
2. Click "Sign Up"
3. Connect with GitHub
4. Click "New +" → "Web Service"
5. Select your "facial" repository
6. Fill in:
   Name: facial-api
   Environment: Python 3.11
   Build Command: pip install -r backend/requirements.txt
   Start Command: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
7. Click "Create Web Service"
8. Scroll to "Environment"
9. Add these variables:
   DATABASE_URL = postgresql://postgres:YOUR_PASSWORD@db.YOUR_REGION.supabase.co:5432/postgres
   CORS_ORIGINS = http://localhost:3000
   DEBUG = False
10. Click "Save"
11. ⏳ Wait 5-10 minutes for deployment
12. ✅ SAVE YOUR BACKEND URL! (e.g., https://facial-api.onrender.com)
```

---

## PHASE 2C: Test Backend Deployment

```powershell
# Test health endpoint (replace with your Render URL)
curl https://facial-api.onrender.com/health

# Should return:
# {"status":"ok","timestamp":"2026-08-14T..."}

# Visit Swagger docs in browser:
# https://facial-api.onrender.com/docs
```

---

## PHASE 3A: Configure Frontend Environment

```powershell
# Navigate to frontend
cd c:\Users\mkiru\facial\facial-recognition-dashboard

# Create .env.local for development
notepad .env.local
# Add:
# NEXT_PUBLIC_API_URL=http://localhost:8000
# NEXT_PUBLIC_WS_URL=ws://localhost:8000
# Save (Ctrl+S) and close

# Create .env.production for production
notepad .env.production
# Add:
# NEXT_PUBLIC_API_URL=https://facial-api.onrender.com
# NEXT_PUBLIC_WS_URL=wss://facial-api.onrender.com
# Save and close
```

---

## PHASE 3B: Push Updated Config to GitHub

```powershell
cd c:\Users\mkiru\facial

git add .
git commit -m "Configure Render backend URL for Vercel deployment"
git push
```

---

## PHASE 3C: Deploy Frontend to Vercel (Do in Web Browser)

```
1. Go to: https://vercel.com
2. Click "Sign Up"
3. Connect with GitHub
4. Click "Add New" → "Project"
5. Select "facial" repository
6. Configure:
   Framework: Next.js (auto-detected)
   Root Directory: facial-recognition-dashboard
   Build Command: pnpm build (or: npm run build)
7. Add Environment Variables:
   NEXT_PUBLIC_API_URL = https://facial-api.onrender.com
   NEXT_PUBLIC_WS_URL = wss://facial-api.onrender.com
8. Click "Deploy"
9. ⏳ Wait 3-5 minutes
10. ✅ SAVE YOUR FRONTEND URL! (e.g., https://facial-recognition-abc123.vercel.app)
```

---

## PHASE 4: Update Render CORS (Do in Web Browser)

```
1. Go to: https://render.com/dashboard
2. Select "facial-api" service
3. Click "Settings"
4. Find "Environment" section
5. Update CORS_ORIGINS to:
   https://facial-recognition-abc123.vercel.app,https://www.facial-recognition-abc123.vercel.app
   (Replace with your actual Vercel URL)
6. Click "Save"
7. ⏳ Wait 1-2 minutes for auto-redeploy
8. ✅ Done!
```

---

## PHASE 4B: Test Full Integration

```powershell
# Test in PowerShell
curl https://facial-api.onrender.com/health

# Then in browser:
# 1. Visit your Vercel URL
# 2. Open DevTools (F12)
# 3. Go to Network tab
# 4. Refresh page
# 5. Should see API calls to your Render backend ✓
# 6. No CORS errors in console ✓
# 7. No errors in Network tab ✓
```

---

## PHASE 5A: Load CSV Data (Optional)

```powershell
# Set Supabase connection string
$env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@db.YOUR_REGION.supabase.co:5432/postgres"

# Navigate to ingestion script
cd c:\Users\mkiru\facial\backend\tasks

# Run ingestion
python ingest_csv.py --database-url $env:DATABASE_URL

# Wait for completion
# Should see: "Ingestion complete! Inserted: 4866"
```

---

## PHASE 5B: Verify Data in Dashboard

```
1. Visit your Vercel frontend URL
2. Refresh the page
3. Should see data in:
   - KPIs (top cards)
   - Face Logs table
   - Cameras section
   - Real-time alerts
4. ✅ Success!
```

---

## TROUBLESHOOTING COMMANDS

```powershell
# Test Supabase connection
$env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@db.YOUR_REGION.supabase.co:5432/postgres"
psql $env:DATABASE_URL -c "SELECT COUNT(*) FROM cameras;"

# View backend logs (Render)
# Go to: https://render.com/dashboard
# Select facial-api service
# Click "Logs" tab

# View frontend build logs (Vercel)
# Go to: https://vercel.com/dashboard
# Select facial-recognition project
# Click "Deployments"
# View build details

# Clear frontend cache
# In DevTools: Network → Disable cache
# Or: Shift + Ctrl + R to hard refresh
```

---

## ALL YOUR IMPORTANT URLS & PASSWORDS

**Keep these somewhere safe!**

```
🔐 Supabase Connection String:
postgresql://postgres:YOUR_PASSWORD@db.YOUR_REGION.supabase.co:5432/postgres

🔗 Backend URL (Render):
https://facial-api.onrender.com

🔗 Frontend URL (Vercel):
https://facial-recognition-abc123.vercel.app

📚 API Documentation:
https://facial-api.onrender.com/docs

💻 GitHub Repository:
https://github.com/YOUR_USERNAME/facial
```

---

## 📋 QUICK CHECKLIST

```
Before Starting:
☐ GitHub account created
☐ Supabase account ready
☐ Render account ready
☐ Vercel account ready

Phase 0 - GitHub:
☐ git init
☐ git add .
☐ git commit
☐ git push to GitHub

Phase 1 - Supabase:
☐ Account created
☐ Project created
☐ Connection string copied
☐ pgvector enabled
☐ SQL tables created
☐ CONNECTION STRING SAVED

Phase 2 - Render:
☐ Account created
☐ Web Service created
☐ DATABASE_URL set
☐ CORS_ORIGINS set
☐ Deployment complete
☐ Health check passing
☐ BACKEND URL SAVED

Phase 3 - Vercel:
☐ Account created
☐ Project imported
☐ Environment variables set
☐ Deployment complete
☐ FRONTEND URL SAVED

Phase 4 - Connect:
☐ Render CORS updated with Vercel URL
☐ Render redeployed
☐ No CORS errors in browser
☐ WebSocket connects

Phase 5 - Data:
☐ CSV imported (optional)
☐ Dashboard shows data
☐ All KPIs displaying
☐ Real-time updates working
```

---

## 🎯 NEXT STEP

**Open:** `COMPLETE_DEPLOYMENT_STEPS.md`

Follow the detailed step-by-step instructions.

Use this file as a quick reference for commands!

**You've got all the code. Now just deploy it!** 🚀
