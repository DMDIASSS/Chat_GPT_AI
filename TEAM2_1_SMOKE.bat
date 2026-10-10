@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u teamplay_v2.py train --samples 256 --rollout 32 --episodes 120 --run-dir data\teamplay_v2\cycle9_smoke
if errorlevel 1 echo SMOKE FAILED. Send traceback; do not start full training.
pause
