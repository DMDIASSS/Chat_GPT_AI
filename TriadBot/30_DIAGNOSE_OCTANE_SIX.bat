@echo off
setlocal
cd /d "%~dp0"
echo Pause selector06 first. Read-only 98 short games compare selector and each fixed expert.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-six-diagnose --run selector06 --pairs 1 --seconds 15
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SIX_WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
