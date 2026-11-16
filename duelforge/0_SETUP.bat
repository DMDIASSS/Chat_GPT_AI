@echo off
cd /d "%~dp0"
py -3.11 tools\setup_project.py
if errorlevel 1 echo SETUP_FAILED - keep the output above. No training started.
pause
