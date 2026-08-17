#!/usr/bin/env powershell
<#
    Quick Deployment Checklist
    Deploy to: Supabase + Render + Vercel
#>

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  CLOUD DEPLOYMENT CHECKLIST" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "📋 Step 1: Setup Supabase (5 min)" -ForegroundColor Yellow
Write-Host "  [ ] Go to https://supabase.com" -ForegroundColor White
Write-Host "  [ ] Create new project → Copy connection string" -ForegroundColor White
Write-Host "  [ ] Enable pgvector extension" -ForegroundColor White
Write-Host "  [ ] Run SQL schema from DEPLOYMENT_GUIDE.md" -ForegroundColor White
Write-Host ""

Write-Host "🖥️  Step 2: Deploy Backend to Render (10 min)" -ForegroundColor Yellow
Write-Host "  [ ] Push code to GitHub" -ForegroundColor White
Write-Host "      git add . && git commit -m 'Deploy' && git push" -ForegroundColor Gray
Write-Host "  [ ] Go to https://render.com → New Web Service" -ForegroundColor White
Write-Host "  [ ] Select your GitHub repo → facial-api" -ForegroundColor White
Write-Host "  [ ] Environment: Python 3.11" -ForegroundColor White
Write-Host "  [ ] Build Command: pip install -r backend/requirements.txt" -ForegroundColor Gray
Write-Host "  [ ] Start Command: cd backend && uvicorn main:app --host 0.0.0.0 --port \$PORT" -ForegroundColor Gray
Write-Host "  [ ] Add env vars:" -ForegroundColor White
Write-Host "      DATABASE_URL=<Supabase connection string>" -ForegroundColor Gray
Write-Host "      DEBUG=False" -ForegroundColor Gray
Write-Host "  [ ] Deploy & wait 3-5 minutes" -ForegroundColor White
Write-Host "  [ ] Copy service URL: https://facial-api.onrender.com" -ForegroundColor White
Write-Host "  [ ] Test: curl https://facial-api.onrender.com/health" -ForegroundColor Gray
Write-Host ""

Write-Host "🎨 Step 3: Deploy Frontend to Vercel (10 min)" -ForegroundColor Yellow
Write-Host "  [ ] Update .env.production in facial-recognition-dashboard/" -ForegroundColor White
Write-Host "      NEXT_PUBLIC_API_URL=https://facial-api.onrender.com" -ForegroundColor Gray
Write-Host "      NEXT_PUBLIC_WS_URL=wss://facial-api.onrender.com" -ForegroundColor Gray
Write-Host "  [ ] Git push" -ForegroundColor White
Write-Host "  [ ] Go to https://vercel.com → Import Project" -ForegroundColor White
Write-Host "  [ ] Select your GitHub repo" -ForegroundColor White
Write-Host "  [ ] Root Directory: facial-recognition-dashboard" -ForegroundColor White
Write-Host "  [ ] Add env vars (same as above)" -ForegroundColor White
Write-Host "  [ ] Deploy & wait 2-3 minutes" -ForegroundColor White
Write-Host "  [ ] Copy your URL: https://yourproject.vercel.app" -ForegroundColor White
Write-Host ""

Write-Host "🔗 Step 4: Connect Everything" -ForegroundColor Yellow
Write-Host "  [ ] Go back to Render dashboard" -ForegroundColor White
Write-Host "  [ ] Update CORS_ORIGINS env var:" -ForegroundColor White
Write-Host "      https://yourproject.vercel.app,https://www.yourproject.vercel.app" -ForegroundColor Gray
Write-Host "  [ ] Save (auto-redeploys)" -ForegroundColor White
Write-Host ""

Write-Host "✅ Step 5: Verify Deployment" -ForegroundColor Yellow
Write-Host "  [ ] Visit https://yourproject.vercel.app" -ForegroundColor White
Write-Host "  [ ] Open browser DevTools → Network tab" -ForegroundColor White
Write-Host "  [ ] Check API calls to backend (should show 200)" -ForegroundColor White
Write-Host "  [ ] WebSocket should connect without errors" -ForegroundColor White
Write-Host ""

Write-Host "📊 Step 6: Load Data (Optional)" -ForegroundColor Yellow
Write-Host "  [ ] Update backend/tasks/ingest_csv.py with your settings" -ForegroundColor White
Write-Host "  [ ] Run locally:" -ForegroundColor White
Write-Host "      python backend/tasks/ingest_csv.py" -ForegroundColor Gray
Write-Host "  [ ] Verify data in Supabase dashboard" -ForegroundColor White
Write-Host ""

Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  🎉 You're Live!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Frontend: https://yourproject.vercel.app" -ForegroundColor Blue
Write-Host "Backend API: https://facial-api.onrender.com" -ForegroundColor Blue
Write-Host "API Docs: https://facial-api.onrender.com/docs" -ForegroundColor Blue
Write-Host "Database: Supabase console" -ForegroundColor Blue
Write-Host ""
Write-Host "See DEPLOYMENT_GUIDE.md for detailed instructions" -ForegroundColor Gray
Write-Host ""
