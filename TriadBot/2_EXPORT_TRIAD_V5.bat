@echo off
cd /d "%~dp0"
"..\novaforge\.venv\Scripts\python.exe" run.py export
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo TRIAD_FAILED - Install or update sibling novaforge first.
pause
exit /b 1
