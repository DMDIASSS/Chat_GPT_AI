@echo off
setlocal
cd /d "%~dp0"
echo Pause selector04 first. Default Breakout diagnostic now has 56 short games including fixed Fusion.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-diagnose --run selector04 --pairs 1 --seconds 30
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
