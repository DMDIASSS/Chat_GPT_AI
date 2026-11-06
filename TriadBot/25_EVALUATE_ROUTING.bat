@echo off
setlocal
cd /d "%~dp0"
echo Pause selector04 with 19 first and wait for saving. This compares routing; it does not train.
echo Five conditions, 40 short games. Keep the report ZIP printed at the end.
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
"..\novaforge\.venv\Scripts\python.exe" -u run.py selector-routing-evaluate --run selector04 --pairs 1 --seconds 30
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo ROUTING_FAILED - keep the error above.
pause
exit /b 1
