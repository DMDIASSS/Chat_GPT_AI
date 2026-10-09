@echo off
setlocal
cd /d "%~dp0"
title Chat GPT AI - Original Nexto vs Original Nexto
if not exist ".venv\Scripts\python.exe" goto missing
echo Watching SAME original Nexto model on BOTH teams (not student V2).
".venv\Scripts\python.exe" -u watch_latest_ai.py --model nexto --actions sample --start kickoff --show-every 60
set "status=%errorlevel%"
echo.
echo Viewer exit code: %status%
pause
exit /b %status%
:missing
echo Missing .venv\Scripts\python.exe
pause
exit /b 1
