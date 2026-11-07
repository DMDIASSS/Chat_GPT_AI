@echo off
setlocal
cd /d "%~dp0"
echo Find and watch the exact Chronos trial 62 actor: +4.7 points, unverified.
echo Training stays paused. A missing actor is reported; another bot is never substituted.
call "%~dp0_RUN.bat" run watch --run research02 --family chronos --trial 62
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo EXACT_TRIAL_NOT_OPENED - keep the error above and the lookup report.
pause
exit /b 1
