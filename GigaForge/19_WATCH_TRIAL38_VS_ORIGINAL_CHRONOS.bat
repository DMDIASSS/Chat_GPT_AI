@echo off
setlocal
cd /d "%~dp0"
echo Blue: trained Chronos trial 38. Orange: original Chronos. Both use Breakout.
echo Training stays paused. Ctrl+C stops viewing.
call "%~dp0_RUN.bat" run watch --run research02 --family chronos --trial 38 --opponent chronos
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WATCH_FAILED - keep the output above. Models and training state were preserved.
pause
exit /b 1
