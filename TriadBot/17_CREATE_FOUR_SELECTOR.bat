@echo off
setlocal
cd /d "%~dp0"
echo After refinement finishes, freeze its retained champion into a separate four-expert selector run.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-four-create --run selector04
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
