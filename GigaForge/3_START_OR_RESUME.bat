@echo off
setlocal
cd /d "%~dp0"
echo Resume the active research run. Use 17_START_AUTONOMOUS_RESEARCH.bat once to start research02.
call "%~dp0_RUN.bat" run research
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
