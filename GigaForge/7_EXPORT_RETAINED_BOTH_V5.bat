@echo off
setlocal
cd /d "%~dp0"
echo Export both protected champions for RLBot v5.
call "%~dp0_RUN.bat" run export
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
