@echo off
setlocal
cd /d "%~dp0"
echo Train/resume selector06. Frozen experts; Fusion-biased initialization. Runs until paused or regression stop.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-train --run selector06 --wandb online
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SIX_WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
