@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Extract into your Chat_GPT_AI project folder.& pause& exit /b 1)
echo Replaying the best SkillForge search attempt in SLOW MOTION. No training.
".venv\Scripts\python.exe" -u skillforge_watch.py --mode best --speed 0.5 --repeat 8
if errorlevel 1 echo Viewer failed. Read the error above.
pause
