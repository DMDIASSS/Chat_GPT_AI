@echo off
setlocal
cd /d "%~dp0"
echo Find and reuse compatible large libraries; CPU mode.
call "%~dp0_RUN.bat" setup --cpu
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
