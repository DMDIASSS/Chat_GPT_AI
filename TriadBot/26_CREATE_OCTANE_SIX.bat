@echo off
setlocal
cd /d "%~dp0"
echo Pause selector04 first. Keeps its exact frozen Fusion; creates a NEW Octane six-expert gate.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-six-create --run selector06 --source selector04
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SIX_WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
