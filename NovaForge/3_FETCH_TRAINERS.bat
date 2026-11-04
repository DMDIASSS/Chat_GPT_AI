@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py fetch-teachers --names nexto,ripple
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py doctor --teachers nexto,ripple
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pytest tests -q --teachers
if errorlevel 1 goto failed
echo TRAINERS_PASS - Read START_HERE.md for teacher pretraining and PPO commands.
pause
exit /b 0
:failed
echo TRAINERS_FAILED - See error above. Missing trainers are never silently replaced.
pause
exit /b 1
