@echo off
setlocal
cd /d "%~dp0"
call FREESTYLE_NATIVE.bat build %*
set "FREESTYLE_EXIT=%ERRORLEVEL%"
pause
endlocal & exit /b %FREESTYLE_EXIT%
