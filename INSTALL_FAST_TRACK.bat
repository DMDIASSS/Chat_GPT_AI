@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_FAST_TRACK.ps1"
if errorlevel 1 (
 echo ERROR: Installation failed. Read the error above.
 pause
 exit /b 1
)
pause
