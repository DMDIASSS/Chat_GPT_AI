@echo off
setlocal
cd /d "%~dp0"
echo Export retained six-expert Octane champion for RLBot v5. Includes exact local frozen Fusion.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py export --selector runs/selector06/champion.pt
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo SIX_WORKFLOW_FAILED - keep the error above.
pause
exit /b 1
