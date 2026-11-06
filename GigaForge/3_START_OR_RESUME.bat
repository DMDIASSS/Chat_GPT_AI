@echo off
setlocal
cd /d "%~dp0"
echo Start or resume native training; keep existing checkpoints and W&B run.
call "%~dp0_RUN.bat" run train
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
