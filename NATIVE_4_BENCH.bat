@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u GigaLearn_Project\Native_Backend\native_setup.py bench --run native_bench01 --device cpu --games 32 --steps 16384 --iterations 6
pause
