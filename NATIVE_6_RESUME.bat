@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u GigaLearn_Project\Native_Backend\native_setup.py resume --run native_train01 --iterations 10
pause
