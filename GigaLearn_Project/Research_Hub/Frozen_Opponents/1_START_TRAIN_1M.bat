@echo off
setlocal
cd /d "%~dp0"
call 0_SETUP_EXTENDED.bat
if errorlevel 1 (
 echo SETUP FAILED: Your existing models were not changed.
 pause
 exit /b 1
)
echo.
echo Starting / resuming five complete rotations: Nexto - Cycle9 - Wavedash
py -3.11 -u extended_rotation.py start --rounds 5
if errorlevel 1 (
 echo.
 echo TRAINING FAILED OR INCOMPLETE. Check your experiment reports. Existing models are protected.
 pause
 exit /b 1
)
echo.
echo Training finished or safely paused. Use 3_CHECK_STATUS.bat for details.
pause
