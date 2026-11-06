@echo off
setlocal
cd /d "%~dp0"
echo Pause selector06 with 28 first. Restores the base opponent distribution on the next resume.
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-sampling-disable --run selector06
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SAMPLING_CONFIGURATION_FAILED - keep the error above.
pause
exit /b 1
