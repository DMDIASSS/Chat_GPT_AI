@echo off
setlocal
cd /d "%~dp0"
py -3.11 frozen_cli.py preflight
if errorlevel 1 (
 echo PRE-FLIGHT FAILED. Read the error above. Check Nexto and Wavedash checkpoints.
 pause
 exit /b 1
)
echo PASS: Native teacher checkpoint formats are compatible.
pause
