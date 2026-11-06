@echo off
setlocal
cd /d "%~dp0"
call "%~dp0_RUN.bat" run train --run native01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo LEGACY_RUN_STOPPED - existing guard is preserved. Use 3 for the new research system.
pause
exit /b 1
