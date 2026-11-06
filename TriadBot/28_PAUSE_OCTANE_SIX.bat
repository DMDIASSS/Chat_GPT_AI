@echo off
setlocal
cd /d "%~dp0"
echo Request selector06 pause. Wait for the training console to finish saving.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-pause --run selector06
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SIX_WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
