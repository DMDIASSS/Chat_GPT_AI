@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py chronos-export --run chronos01
pause
