@echo off
setlocal
cd /d "%~dp0"
echo SELECTOR DIAGNOSTICS - pause with 8 and wait for saving first.
echo Default: 48 games, 30 simulated seconds each for a Breakout selector.
echo Measures free-choice probabilities, fixed experts and reference hitboxes.
echo No training or checkpoint changes. Ctrl+C cancels.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-diagnose --pairs 1 --seconds 30
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo DIAGNOSTICS_FAILED - keep the error above.
pause
exit /b 1
