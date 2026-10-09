@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Extract into Chat_GPT_AI project first.& pause& exit /b 1)
".venv\Scripts\python.exe" -u sf2_watch.py --mode best --speed 0.4 --repeat 6
if errorlevel 1 echo Viewer problem. Send full error.
pause
