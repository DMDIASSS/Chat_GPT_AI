@echo off
setlocal
cd /d "%~dp0"
echo Watch current Chronos candidate on Breakout.
call "%~dp0_RUN.bat" run watch --family chronos --candidate
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
