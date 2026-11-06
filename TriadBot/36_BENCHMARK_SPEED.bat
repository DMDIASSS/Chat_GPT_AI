@echo off
setlocal
cd /d "%~dp0"
echo Pause training first. Measures native environment decisions per second without training.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-benchmark --run selector06 --steps 2048
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
