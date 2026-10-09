@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Extract this add-on into the existing Chat GPT AI project folder.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -c "from chatgpt_ai.config import PRESETS; assert 'grounded' in PRESETS, 'Install Grounded Upgrade first'"
if errorlevel 1 (
 echo ERROR: Grounded preset missing.
 pause
 exit /b 1
)
echo Collecting 5000 Nexto self-controlled RocketSim decision ticks (~10000 car samples).
echo You can collect more after verifying this first run.
".venv\Scripts\python.exe" collect_nexto_rollouts.py --max-decisions 5000 --episode-decisions 450 --save-every 5000 --scenarios grounded --teacher-device cpu
if errorlevel 1 echo ERROR: Rollout failed; send the full traceback for debugging.
pause
