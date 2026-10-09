@echo off
setlocal
cd /d "%~dp0"
.venv\Scripts\python.exe autoleague_status.py
pause
