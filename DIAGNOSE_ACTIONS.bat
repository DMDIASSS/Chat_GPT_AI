@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe diagnose_actions.py --samples 3000
pause
