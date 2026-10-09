$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
py -3.11 -m venv .venv
$Python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $Python -m pip install --upgrade pip setuptools wheel
# cu126 requires a compatible NVIDIA GPU and driver; change index at pytorch.org if needed.
& $Python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
& $Python -m pip install -r requirements-train.txt
& $Python doctor.py
Write-Host 'Install extras when needed: .\.venv\Scripts\python.exe -m pip install -r requirements-extra.txt'
