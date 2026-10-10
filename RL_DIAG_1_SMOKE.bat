@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: .venv\Scripts\python.exe is missing.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u rl_scenario_diagnostics.py --smoke
if errorlevel 1 echo SIMULATOR SMOKE FAILED. Do not start a long benchmark.
pause
