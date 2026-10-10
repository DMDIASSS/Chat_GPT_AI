@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0afk_package_reports.ps1"
if errorlevel 1 echo Packaging failed. See above.
pause
