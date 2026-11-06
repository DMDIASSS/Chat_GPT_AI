@echo off
setlocal
cd /d "%~dp0"
echo Request a safe pause. Wait for the training console to print FORGE_REPORT before copying files.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py pause --run duel01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo FORGE_COMMAND_FAILED - keep the error above.
pause
exit /b 1
