@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u diagnose_native_exports.py
pause
