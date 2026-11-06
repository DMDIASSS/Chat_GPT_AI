@echo off
setlocal
cd /d "%~dp0"
echo Start or resume research01 reward search; keep existing native01 and protected champions.
call "%~dp0_RUN.bat" run research --run research01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. Existing models and runs were preserved.
pause
exit /b 1
