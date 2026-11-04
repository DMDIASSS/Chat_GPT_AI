@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -u run.py train --run laptop01 --init models\ripple_bc.zip --teachers nexto,ripple --steps 100000
if errorlevel 1 goto failed
echo Training segment complete. Use 7_RESUME.bat for more training.
pause
exit /b 0
:failed
echo TRAIN_FAILED - If laptop01 already exists, use 7_RESUME.bat instead.
pause
exit /b 1
