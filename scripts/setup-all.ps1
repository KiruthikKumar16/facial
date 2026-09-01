#!/usr/bin/env powershell
<#
    Setup and run backend + frontend in parallel
#>

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "FACIAL RECOGNITION SYSTEM STARTUP" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Backend setup
Write-Host "📦 Step 1: Installing backend dependencies..." -ForegroundColor Yellow
Push-Location backend
if (-not (Test-Path "venv")) {
    python -m venv venv
}
& .\venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
Pop-Location
Write-Host "✅ Backend ready" -ForegroundColor Green
Write-Host ""

# Step 2: Frontend setup
Write-Host "📦 Step 2: Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location facial-recognition-dashboard
$pnpmExists = $null -ne (Get-Command pnpm -ErrorAction SilentlyContinue)
if ($pnpmExists) {
    pnpm install
} else {
    Write-Host "⚠️  pnpm not found, using npm (slower)..." -ForegroundColor Yellow
    npm install
}
Pop-Location
Write-Host "✅ Frontend ready" -ForegroundColor Green
Write-Host ""

# Step 3: Database warning
Write-Host "⚠️  IMPORTANT: Database Setup" -ForegroundColor Yellow
Write-Host "   Ensure PostgreSQL is running locally:" -ForegroundColor White
Write-Host "   - Host: localhost" -ForegroundColor White
Write-Host "   - User: postgres" -ForegroundColor White
Write-Host "   - Password: postgres" -ForegroundColor White
Write-Host "   - Database: facial_recognition" -ForegroundColor White
Write-Host ""
Write-Host "   Run: createdb facial_recognition" -ForegroundColor Gray
Write-Host ""

# Step 4: Show launch commands
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "🚀 READY TO LAUNCH" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "In separate terminals, run:" -ForegroundColor White
Write-Host ""
Write-Host "  📡 BACKEND (API + WebSocket):" -ForegroundColor Green
Write-Host "     cd backend && python main.py" -ForegroundColor Gray
Write-Host "     → http://localhost:1223" -ForegroundColor Gray
Write-Host "     → ws://localhost:1223/ws/alerts (WebSocket)" -ForegroundColor Gray
Write-Host ""
Write-Host "  🎨 FRONTEND (React Dashboard):" -ForegroundColor Blue
Write-Host "     cd facial-recognition-dashboard && pnpm dev" -ForegroundColor Gray
Write-Host "     → http://localhost:3000" -ForegroundColor Gray
Write-Host ""
