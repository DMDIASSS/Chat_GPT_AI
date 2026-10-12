@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Missing .venv\Scripts\python.exe in %CD%
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u slater_v041_overnight.py start
echo.
if errorlevel 1 echo FAILED - inspect error message and logs before leaving unattended.
pause
