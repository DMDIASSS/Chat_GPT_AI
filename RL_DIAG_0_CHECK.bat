@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: project virtualenv not found: .venv\Scripts\python.exe
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u rl_scenario_diagnostics.py --check
if errorlevel 1 echo PREFLIGHT FAILED. Send the error to ChatGPT.
pause
