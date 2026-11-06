@echo off
setlocal
cd /d "%~dp0"
echo Two independent actors: controlled pilot, frozen-opponent league, WDL guards. Runs until paused or a protection stop. Close other training first.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py train --run duel01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo FORGE_COMMAND_FAILED - keep the error above.
pause
exit /b 1
