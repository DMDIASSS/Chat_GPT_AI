@echo off
cd /d "%~dp0"
call _RUN.bat watch --run duel01 --opponent nexto --seconds 120
pause
