@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Extract into your Chat_GPT_AI project folder.& pause& exit /b 1)
echo Replaying best attempts from generations 1 to 6; this is recorded search progress, not retraining.
".venv\Scripts\python.exe" -u skillforge_watch.py --mode progress --speed 0.5 --repeat 2
if errorlevel 1 echo Viewer failed. Read the error above.
pause
