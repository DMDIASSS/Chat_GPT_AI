@echo off
cd /d "%~dp0"
echo Watching full original Nexto attention policy versus frozen Nexto.
.venv\Scripts\python.exe native_nexto.py --mode baseline --render --games 1 --eval-decisions 750 --device cpu
pause
