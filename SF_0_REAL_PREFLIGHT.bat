@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Extract into your existing Chat_GPT_AI project folder.& pause & exit /b 1)
echo SKILLFORGE v1: Real RocketSim flag/dodge validator. NO training.
".venv\Scripts\python.exe" -u skillforge_preflight.py --seeds 6
if errorlevel 1 echo PREFLIGHT FAILED. Please send the full error; do not run search yet.
pause
