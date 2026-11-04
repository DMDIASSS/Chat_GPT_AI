@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pytest tests -q
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py doctor
if errorlevel 1 goto failed
echo CHECK_PASS - Next run 2_SMOKE.bat
pause
exit /b 0
:failed
echo CHECK_FAILED - Keep this console output and do not start a long run yet.
pause
exit /b 1
