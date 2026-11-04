@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py smoke --run smoke_%RANDOM% --workers 2
if errorlevel 1 goto failed
echo SMOKE_PASS - Next run 3_FETCH_TRAINERS.bat
pause
exit /b 0
:failed
echo SMOKE_FAILED - Keep this console output for feedback.
pause
exit /b 1
