@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe watch_latest_ai.py --list
pause
