@echo off
cd /d "%~dp0"
call _RUN.bat evaluate --run duel01 --games 20 --seconds 60
pause
