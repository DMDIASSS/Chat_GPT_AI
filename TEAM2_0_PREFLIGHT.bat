@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u teamplay_v2.py preflight
if errorlevel 1 echo PRE-FLIGHT FAILED. Send the traceback; do not train.
pause
