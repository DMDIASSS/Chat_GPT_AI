@echo off
cd /d "%~dp0"
call _RUN.bat evaluate --run attention01 --rounds 100 --seconds 60
pause
