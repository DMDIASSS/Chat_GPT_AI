@echo off
cd /d "%~dp0"
call _RUN.bat watch --run potential01 --opponent initial --scene 5 --seconds 120
pause
