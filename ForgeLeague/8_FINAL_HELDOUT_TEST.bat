@echo off
setlocal
cd /d "%~dp0"
echo Pause training first. Longer blind test against original Chronos, Galactus, Nexto and Ripple. Does not promote models.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py test --run duel01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo FORGE_COMMAND_FAILED - keep the error above.
pause
exit /b 1
