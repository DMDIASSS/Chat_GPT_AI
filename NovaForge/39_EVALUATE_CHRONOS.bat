@echo off
setlocal
cd /d "%~dp0"
echo Pause with 36 and wait for training to exit before comparing.
".venv\Scripts\python.exe" run.py chronos-evaluate --run chronos01
if errorlevel 1 goto failed
echo Upload the new chronos01 report ZIP from reports.
pause
exit /b 0
:failed
echo CHRONOS_EVALUATION_FAILED - keep this output for diagnosis.
pause
exit /b 1
