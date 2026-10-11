# PhotoApp - instalacao automatica
# Cria o ambiente virtual Python e instala as dependencias.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -AI

param(
  [switch]$AI
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== PhotoApp :: instalacao ==" -ForegroundColor Cyan

# 1) Localiza o Python
$python = "python"
try { & $python --version | Out-Null } catch {
  Write-Host "Python nao encontrado. Instale com: winget install Python.Python.3.12" -ForegroundColor Red
  exit 1
}

# 2) Ambiente virtual
if (-not (Test-Path ".venv")) {
  Write-Host "Criando ambiente virtual .venv ..." -ForegroundColor Yellow
  & $python -m venv .venv
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip

# 3) Dependencias do nucleo
Write-Host "Instalando dependencias do nucleo ..." -ForegroundColor Yellow
& $venvPython -m pip install -r backend\requirements.txt

# 4) Modelos de IA (opcional)
if ($AI) {
  Write-Host "Baixando runtime PyTorch (CPU) ..." -ForegroundColor Yellow
  & $venvPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
  Write-Host "Instalando modelo LaMa (inpainting de textura) ..." -ForegroundColor Yellow
  & $venvPython -m pip install -r backend\requirements-ai.txt
  # Garante a politica de fidelidade: nada de reconstrucao facial generativa.
  & $venvPython -m pip uninstall -y gfpgan codeformer 2>$null
}

# 5) Icones do PWA
if (Get-Command node -ErrorAction SilentlyContinue) {
  node scripts\generate-icons.js
}

Write-Host "Instalacao concluida. Rode: scripts\run.ps1" -ForegroundColor Green
