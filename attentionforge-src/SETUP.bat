@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto fallback
py -3.11 tools\setup_runtime.py
goto finish
:fallback
python tools\setup_runtime.py
:finish
if errorlevel 1 echo SETUP_FAILED - keep the error above. Existing projects were preserved.
pause
