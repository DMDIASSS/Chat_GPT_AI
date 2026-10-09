@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run START_HERE.bat first.
 pause
 exit /b 1
)
echo ===== Chat GPT AI: resume self-play to 50 million steps =====
.venv\Scripts\python.exe train.py --preset balanced --steps 50000000
pause
