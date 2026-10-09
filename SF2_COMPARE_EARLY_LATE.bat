@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Extract into Chat_GPT_AI project first.& pause& exit /b 1)
echo EARLY dodge before contact
".venv\Scripts\python.exe" -u sf2_watch.py --mode early --speed 0.5 --repeat 2
echo LATE dodge closer to contact
".venv\Scripts\python.exe" -u sf2_watch.py --mode late --speed 0.5 --repeat 2
pause
