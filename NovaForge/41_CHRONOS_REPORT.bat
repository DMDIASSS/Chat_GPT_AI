@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py chronos-report --run chronos01
pause
