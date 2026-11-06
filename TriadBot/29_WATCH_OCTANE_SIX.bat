@echo off
setlocal
cd /d "%~dp0"
echo Watch latest six-expert Octane selector. Console shows current expert. Ctrl+C stops.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py watch --selector runs/selector06/latest.pt
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SIX_WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
