@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe export_rlbot_v4.py --list
pause
