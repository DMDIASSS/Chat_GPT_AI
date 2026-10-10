@echo off
setlocal
cd /d "%~dp0"
call 0_SETUP_EXTENDED.bat
if errorlevel 1 (
 echo SETUP FAILED.
 pause
 exit /b 1
)
echo.
echo Running / resuming two three-teacher rounds, ~400k student steps.
py -3.11 -u extended_rotation.py start --rounds 2
if errorlevel 1 (
 echo TRAINING FAILED OR INCOMPLETE. Check reports.
 pause
 exit /b 1
)
pause
