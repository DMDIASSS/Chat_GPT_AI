@echo off
cd /d "%~dp0"
call _RUN.bat evaluate --run potential01 --context match --games 200 --seconds 100
pause
