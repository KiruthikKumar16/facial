#!/usr/bin/env powershell
<#
    Quick start: Launch frontend in current terminal
#>

Write-Host "Starting Frontend..." -ForegroundColor Blue
Write-Host ""
Write-Host "Dashboard will be available at:" -ForegroundColor Cyan
Write-Host "  → http://localhost:3000" -ForegroundColor Gray
Write-Host ""
Write-Host "🔗 Make sure backend is running on port 8000!" -ForegroundColor Yellow
Write-Host ""

cd facial-recognition-dashboard

$pnpmExists = $null -ne (Get-Command pnpm -ErrorAction SilentlyContinue)
if ($pnpmExists) {
    pnpm dev
} else {
    npm run dev
}
