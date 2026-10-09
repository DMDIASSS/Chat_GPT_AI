@echo off
cd /d "%~dp0"
title Nexto original vs Nexto original
.venv\Scripts\python.exe watch_latest_ai.py --model nexto --actions sample --start kickoff
pause
