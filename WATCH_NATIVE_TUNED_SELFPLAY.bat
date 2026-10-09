@echo off
setlocal
cd /d "%~dp0"
title Chat GPT AI - Fine-tuned native Nexto selfplay
if not exist "data\native_nexto\last.pt" (
 echo Native fine-tuned weights do not exist yet: data\native_nexto\last.pt
 echo You have only run NATIVE_0_BENCHMARK, which compares original Nexto vs itself.
 echo To view the original use WATCH_NATIVE_NEXTO_SELFPLAY.bat
 pause
 exit /b 1
)
echo Watching latest FINE-TUNED Nexto model on BOTH teams.
".venv\Scripts\python.exe" -u watch_latest_ai.py --model native --actions sample --start kickoff --show-every 60
set "status=%errorlevel%"
echo.
echo Viewer exit code: %status%
pause
exit /b %status%
