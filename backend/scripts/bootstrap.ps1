# Local Windows development bootstrap (the real deployment target is IBM Z / LinuxONE; use
# scripts/bootstrap.sh there — see PRD section 9). This script sets up a working dev environment
# on Windows so the API is runnable and testable before pushing to the VM.

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "== Creating virtualenv (.venv) =="
python -m venv .venv

Write-Host "== Installing pinned dependencies =="
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "== Creating .env from .env.example =="
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null

Write-Host "== Bootstrapping database + demo fixture catalog =="
& .\.venv\Scripts\python.exe -c "from app.bootstrap import bootstrap; bootstrap()"

Write-Host "== Training HDB valuation model (synthetic bootstrap) =="
& .\.venv\Scripts\python.exe -m app.ml.train

Write-Host "== Running test suite =="
& .\.venv\Scripts\python.exe -m pytest -q

Write-Host "== Done. Start the API with: =="
Write-Host "    .\.venv\Scripts\uvicorn.exe app.main:app --reload"
