@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe GigaLearn_Project\Native_Backend\native_setup.py pause --run native_train01
pause
