@echo off
cd /d "%~dp0"
echo Extended finishing benchmark - will take significantly longer.
".venv\Scripts\python.exe" -u finishing_eval.py --pairs 30 --decisions 450
if errorlevel 1 echo Failed. Please send screenshot or full error.
pause
