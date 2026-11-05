@echo off
setlocal
cd /d "%~dp0"
echo TRIAD SELECTOR EVALUATION - 32 games, 60 simulated seconds each.
echo Pause training with 8 and wait for its console to finish first.
echo Loading Python and evaluation models; progress will print below.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-evaluate
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SELECTOR_EVALUATION_FAILED - keep the error above.
pause
exit /b 1
