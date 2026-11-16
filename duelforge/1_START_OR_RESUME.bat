@echo off
cd /d "%~dp0"
call _RUN.bat train --run duel01 --minutes 60
pause
