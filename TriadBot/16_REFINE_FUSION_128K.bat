@echo off
setlocal
cd /d "%~dp0"
echo Bounded refinement: resume toward 131072 total new decisions, with regression protection and self-play.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py fusion-refine-train
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
