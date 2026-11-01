@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_native_teacher_repair.py --compare
pause
