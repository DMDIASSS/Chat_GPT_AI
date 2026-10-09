@echo off
cd /d "%~dp0"
echo REAL RocketSim preflight (all 10 drills, one live physics step each); no training.
".venv\Scripts\python.exe" -u mechanics_doctor.py
if errorlevel 1 (echo STOP: Do not start training. Send traceback.&pause&exit /b 1)
pause
