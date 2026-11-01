@echo off
setlocal
cd /d "%~dp0"
call FREESTYLE_NATIVE.bat status --settings FREESTYLE_SETTINGS.json %*
set "FREESTYLE_EXIT=%ERRORLEVEL%"
pause
endlocal & exit /b %FREESTYLE_EXIT%
