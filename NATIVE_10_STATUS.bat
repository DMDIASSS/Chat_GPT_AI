@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe slater_native_overnight.py status --run native_overnight03
pause
