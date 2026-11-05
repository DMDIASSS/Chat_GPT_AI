@echo off
setlocal
cd /d "%~dp0"
echo 64 games total; both policies, both colors, four opponents. Pause with 8 first.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-evaluate --split validation --pairs 4
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo RESEARCH_COMMAND_FAILED - keep this console output.
pause
exit /b 1
