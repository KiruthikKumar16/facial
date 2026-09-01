#!/usr/bin/env powershell
<#
    Quick start: Launch backend in current terminal
    Run frontend separately
#>

Write-Host "Starting Backend..." -ForegroundColor Green
Write-Host ""
Write-Host "API will be available at:" -ForegroundColor Cyan
Write-Host "  → http://localhost:1223" -ForegroundColor Gray
Write-Host "  → API Docs: http://localhost:1223/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "WebSocket endpoints:" -ForegroundColor Cyan
Write-Host "  → ws://localhost:1223/ws/alerts" -ForegroundColor Gray
Write-Host "  → ws://localhost:1223/ws/cameras" -ForegroundColor Gray
Write-Host "  → ws://localhost:1223/ws/kpis" -ForegroundColor Gray
Write-Host ""
Write-Host "⚠️  Make sure PostgreSQL is running!" -ForegroundColor Yellow
Write-Host ""

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "myenv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Project Python environment not found at $python"
}

Push-Location (Join-Path $root "backend")
try {
    $env:PORT = "1223"
    & $python main.py
} finally {
    Pop-Location
}
