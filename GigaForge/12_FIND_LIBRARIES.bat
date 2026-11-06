@echo off
setlocal
cd /d "%~dp0"
echo Find existing libraries and Python environments; do not install or delete anything.
call "%~dp0_RUN.bat" find
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
