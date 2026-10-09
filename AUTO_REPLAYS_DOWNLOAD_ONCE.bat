@echo off
setlocal
cd /d "%~dp0"
if "%BALLCHASING_TOKEN%"=="" (
    echo BALLCHASING_TOKEN is missing. See README_AUTOLEAGUE.md. Download skipped.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -u run_replays_once.py
pause
