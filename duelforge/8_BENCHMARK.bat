@echo off
cd /d "%~dp0"
call _RUN.bat benchmark --seconds 5
pause
