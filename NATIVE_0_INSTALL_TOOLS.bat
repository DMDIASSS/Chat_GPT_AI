@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m pip install -r GigaLearn_Project\Native_Backend\requirements.txt
.venv\Scripts\python.exe GigaLearn_Project\Native_Backend\native_setup.py check
pause
