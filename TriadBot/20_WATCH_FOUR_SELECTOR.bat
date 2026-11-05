@echo off
setlocal
cd /d "%~dp0"
echo Watches latest selector04, including actual learned choice probabilities.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py watch --selector runs/selector04/latest.pt
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
