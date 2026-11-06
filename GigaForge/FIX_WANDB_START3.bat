@echo off
setlocal
cd /d "%~dp0"
echo Repair W^&B in the same runtime the start launcher uses.
call "%~dp0_RUN.bat" repair-wandb
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
