@echo off
setlocal
cd /d "%~dp0"
call _RUN.bat evaluate --run contact01/02_possession --context match --games 200 --seconds 100
pause
