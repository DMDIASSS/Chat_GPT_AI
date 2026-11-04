@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -u run.py train --run diverse01 --config configs\diverse.json --init models\mixed_bc.zip --steps 100000
if errorlevel 1 goto failed
echo Training segment complete. Use 14_MIXED_RESUME.bat to continue.
pause
exit /b 0
:failed
echo TRAIN_FAILED - If diverse01 exists, use 14_MIXED_RESUME.bat instead.
pause
exit /b 1
