@echo off
setlocal
cd /d "%~dp0"
echo Find and reuse compatible CUDA PyTorch libraries; verify the actual GPU path.
call "%~dp0_RUN.bat" setup
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
