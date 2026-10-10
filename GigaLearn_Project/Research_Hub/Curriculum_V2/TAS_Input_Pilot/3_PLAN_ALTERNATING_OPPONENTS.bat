@echo off
setlocal
set "PILOT=%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 not found & pause & exit /b 1)
"%PY%" "%PILOT%tas_pilot.py" plan-opponents --output "%PILOT%alternating_opponents_plan.json" --cycles 3 --games-per-opponent 4
if errorlevel 1 (echo Failed to generate plan & pause & exit /b 1)
echo Generated opponent training PLAN ONLY. No real Nexto matches until bridge is built.
pause
