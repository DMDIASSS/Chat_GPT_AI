@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Project .venv\Scripts\python.exe missing.
 pause
 exit /b 2
)
".venv\Scripts\python.exe" -u finishing_train.py --mode check
if errorlevel 1 echo FAILED: do not start training until this is fixed.
pause
