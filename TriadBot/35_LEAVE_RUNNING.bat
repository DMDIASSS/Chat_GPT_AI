@echo off
setlocal
cd /d "%~dp0"
echo Pause other training with 28 first. One unattended selector job; reports and champion exports automatic.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-autopilot --run selector06 --wandb online
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
