@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Put this upgrade into the existing Chat_GPT_AI folder, next to train.py and .venv.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" fast_track_doctor.py --engine-smoke
if errorlevel 1 (
 echo ERROR: Doctor failed. Send this output before running large jobs.
 pause
 exit /b 1
)
pause
