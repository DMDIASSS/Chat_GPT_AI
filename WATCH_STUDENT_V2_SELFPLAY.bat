@echo off
setlocal
cd /d "%~dp0"
title Chat GPT AI - Distilled Student V2 selfplay
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -u watch_latest_ai.py --model student --actions sample --start kickoff --show-every 60
set "status=%errorlevel%"
echo.
echo Viewer exit code: %status%
pause
exit /b %status%
:missing
echo Missing .venv
pause
exit /b 1
