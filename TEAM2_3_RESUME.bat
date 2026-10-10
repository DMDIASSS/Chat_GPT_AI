@echo off
cd /d "%~dp0"
if exist "data\teamplay_v2\cycle9_shared_2v2\STOP_AFTER_ROLLOUT" (echo Remove STOP_AFTER_ROLLOUT before resuming. & pause & exit /b 1)
".venv\Scripts\python.exe" -u teamplay_v2.py train --samples 16384 --rollout 128 --episodes 330 --run-dir data\teamplay_v2\cycle9_shared_2v2 --resume
pause
