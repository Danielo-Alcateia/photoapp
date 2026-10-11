# PhotoApp - execucao
# Sobe o servidor Flask (frontend PWA + API) e abre o navegador.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\run.ps1 -Port 8000 -NoBrowser

param(
  [int]$Port = 8000,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  Write-Host "Ambiente .venv nao encontrado. Rode scripts\install.ps1 primeiro." -ForegroundColor Red
  exit 1
}

$env:PORT = "$Port"

if (-not $NoBrowser) {
  Start-Job -ScriptBlock {
    param($p)
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:$p"
  } -ArgumentList $Port | Out-Null
}

Write-Host "PhotoApp rodando em http://localhost:$Port" -ForegroundColor Green
& $venvPython backend\app.py
