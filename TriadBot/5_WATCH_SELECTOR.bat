@echo off
cd /d "%~dp0"
"..\novaforge\.venv\Scripts\python.exe" run.py watch --selector runs/selector01/latest.pt
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SELECTOR_COMMAND_FAILED - keep this output.
pause
exit /b 1
