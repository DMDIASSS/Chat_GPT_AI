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
echo Extending to 15 complete Nexto / Cycle9 / Wavedash rounds total.
py -3.11 -u extended_rotation.py start --rounds 15
if errorlevel 1 (
 echo TRAINING FAILED OR INCOMPLETE. Check reports; existing models are protected.
 pause
 exit /b 1
)
pause
