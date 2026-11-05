@echo off
setlocal
cd /d "%~dp0"
echo Pause with 8 first. Produces a small ZIP without model weights or raw logs.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py research-report
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo RESEARCH_COMMAND_FAILED - keep this console output.
pause
exit /b 1
