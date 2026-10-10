@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Missing project .venv & pause & exit /b 1)
echo Requesting safe pause in the latest active AFK job...
".venv\Scripts\python.exe" -u afk_pause_request.py
if errorlevel 1 echo No active AFK job found or pause request failed.
pause
