@echo off
setlocal
cd /d "%~dp0"
echo Pause original Fusion with NovaForge 44 and wait. Tests available saved Fusion students, with fresh confirmation.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py fusion-select --pairs 1 --seconds 30 --confirmation-pairs 2 --confirmation-seconds 60
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
