@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: PREPARE_TRAINING.bat "C:\path\to\RoWorld.rbxl"
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP_TRAINING.bat first.
  exit /b 1
)
.venv\Scripts\python.exe training\prepare.py --place "%~1" --out private\engine.json
exit /b %errorlevel%
