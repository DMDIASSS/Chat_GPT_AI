@echo off
cd /d "%~dp0"
echo Read-only shooting benchmark of Cycle 9, champion, wavedash, and optional finishing candidate.
".venv\Scripts\python.exe" -u finishing_eval.py --pairs 8 --decisions 330
if errorlevel 1 echo Failed. Please send screenshot or full error.
pause
