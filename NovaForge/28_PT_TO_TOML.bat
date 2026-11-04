@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" goto picker
".venv\Scripts\python.exe" run.py pt-to-toml "%~1"
goto done
:picker
".venv\Scripts\python.exe" run.py pt-to-toml
:done
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo PT_PACKAGE_FAILED - Keep the error above. See PT_TO_TOML.md for supported models.
pause
exit /b 1
