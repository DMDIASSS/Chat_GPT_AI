@echo off
setlocal
cd /d "%~dp0"
echo 200 scored games, 100 simulated seconds each, both team colors equally.
echo Strongest available positive confirmation-test candidate versus its original.
echo Close viewers and keep training paused. Ctrl+C pauses this test.
call "%~dp0_RUN.bat" run h2h --run research02 --rounds 200 --seconds 100
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo H2H_FAILED - keep the output. Training models and champions were preserved.
pause
exit /b 1
