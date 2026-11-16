@echo off
setlocal
cd /d "%~dp0"
call _RUN.bat watch --run contact01/02_possession --seconds 120 --scene -2
pause
