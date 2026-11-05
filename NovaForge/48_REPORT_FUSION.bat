@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py chronos-report --run fusion01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo COMMAND_FAILED - Keep the output above.
pause
exit /b 1
