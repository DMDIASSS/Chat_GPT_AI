@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u GigaLearn_Project\Native_Backend\native_setup.py train --run native_train01 --device auto --games 64 --steps 32768 --iterations 10 --width 256 --depth 3
pause
