@echo off
setlocal
cd /d "%~dp0"
echo Trains selector04 only. Chronos, Galactus, Ripple and selected Fusion remain frozen.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-train --run selector04
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
