@echo off
setlocal
cd /d "%~dp0"
echo Stationary Chronos pilot: train. Existing research runs and champions stay unchanged.
call "%~dp0_RUN.bat" pilot train --run stationary01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo PILOT_COMMAND_FAILED - keep the output above.
pause
exit /b 1
