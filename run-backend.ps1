#!/usr/bin/env powershell
<#
    Quick start: Launch backend in current terminal
    Run frontend separately
#>

Write-Host "Starting Backend..." -ForegroundColor Green
Write-Host ""
Write-Host "API will be available at:" -ForegroundColor Cyan
Write-Host "  → http://localhost:8000" -ForegroundColor Gray
Write-Host "  → API Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "WebSocket endpoints:" -ForegroundColor Cyan
Write-Host "  → ws://localhost:8000/ws/alerts" -ForegroundColor Gray
Write-Host "  → ws://localhost:8000/ws/cameras" -ForegroundColor Gray
Write-Host "  → ws://localhost:8000/ws/kpis" -ForegroundColor Gray
Write-Host ""
Write-Host "⚠️  Make sure PostgreSQL is running!" -ForegroundColor Yellow
Write-Host ""

cd backend
python main.py
