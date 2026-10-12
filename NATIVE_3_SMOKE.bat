@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u GigaLearn_Project\Native_Backend\native_setup.py smoke --run native_smoke01 --device cpu
pause
