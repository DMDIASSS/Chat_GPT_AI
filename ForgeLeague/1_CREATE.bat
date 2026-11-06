@echo off
setlocal
cd /d "%~dp0"
echo Creates duel01. Uses selector06 or selector04 frozen Fusion if present, else original Chronos. Does not reset an existing run.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py create --run duel01
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo FORGE_COMMAND_FAILED - keep the error above.
pause
exit /b 1
