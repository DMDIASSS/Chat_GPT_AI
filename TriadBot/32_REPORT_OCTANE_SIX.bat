@echo off
setlocal
cd /d "%~dp0"
echo Create a shareable selector06 research report ZIP.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py research-report --run selector06
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SIX_WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
