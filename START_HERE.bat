@echo off
setlocal
cd /d "%~dp0"
echo ===== Chat GPT AI =====
echo Installing trainer dependencies...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
if errorlevel 1 goto failed
echo Starting 100,000-step training smoke test...
.venv\Scripts\python.exe train.py --preset smoke --steps 100000 --workers 4 --fresh --save-every 50000
if errorlevel 1 goto failed
echo Smoke training finished. Next, use TRAIN_MORE.bat.
pause
exit /b 0
:failed
echo Setup or smoke training failed. Inspect the error messages above.
pause
exit /b 1
