@echo off
cd /d "%~dp0"
echo BLUE and ORANGE use the same frozen latest duel02 checkpoint. Both Octane.
call _RUN.bat watch --run duel02 --opponent self --scene 5 --seconds 120
pause
