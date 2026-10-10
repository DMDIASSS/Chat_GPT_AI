@echo off
cd /d "%~dp0"
echo Checking the first 30 high-priority drills. No training or checkpoint writes.
.venv\Scripts\python.exe -u replay_defense.py fidelity --max-drills 30 --max-ball-error 850
if errorlevel 1 echo CHECK FAILED. Do not train until the replay divergence is resolved.
pause
