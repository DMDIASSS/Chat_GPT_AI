@echo off
setlocal
cd /d "%~dp0"
echo Verify the executable and inspect Windows launch permissions.
call "%~dp0_RUN.bat" native-check
pause
exit /b %errorlevel%
