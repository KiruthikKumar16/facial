#!/usr/bin/env powershell
<#
    Quick start: Launch frontend in current terminal
#>

Write-Host "Starting Frontend..." -ForegroundColor Blue
Write-Host ""
Write-Host "Dashboard will be available at:" -ForegroundColor Cyan
Write-Host "  → http://localhost:3000" -ForegroundColor Gray
Write-Host ""
Write-Host "🔗 Make sure backend is running on port 1223!" -ForegroundColor Yellow
Write-Host ""

$root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $root "facial-recognition-dashboard")
try {
    npm run dev
} finally {
    Pop-Location
}
