@echo off
setlocal
cd /d "%~dp0"
echo Checking native Nexto + real RocketSim physics. No training, no overwritten models.
if not exist .venv\Scripts\python.exe (echo ERROR: Missing project virtual environment. & pause & exit /b 1)
.venv\Scripts\python.exe auto_league.py --preflight --source "data\native_nexto\best_10k.pt"
if errorlevel 1 (echo PREFLIGHT FAILED, do not train. & pause & exit /b 1)
echo Preflight passed. Next: AUTO_1_START.bat
pause
