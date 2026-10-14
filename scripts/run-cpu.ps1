#!/usr/bin/env powershell
<#
    Quick start: Launch CPU facial recognition runner
#>

Write-Host "Starting Facial Recognition (CPU Runner)..." -ForegroundColor Cyan
Write-Host "Press 'q' in any video display window to stop." -ForegroundColor Yellow
Write-Host ""

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "myenv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Project Python environment not found at $python"
}

Push-Location $root
try {
    & $python (Join-Path $root "facial_recognition\run_cpu.py") $args
} finally {
    Pop-Location
}
