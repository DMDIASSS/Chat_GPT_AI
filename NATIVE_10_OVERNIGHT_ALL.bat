@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_native_overnight.py run --run native_overnight02
pause
