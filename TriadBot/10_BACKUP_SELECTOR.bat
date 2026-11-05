@echo off
setlocal
cd /d "%~dp0"
echo Pause with 8 and wait for the training console to finish saving first.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py research-backup
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo RESEARCH_COMMAND_FAILED - keep this console output.
pause
exit /b 1
