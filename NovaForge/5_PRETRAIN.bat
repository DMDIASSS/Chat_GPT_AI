@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py pretrain --dataset datasets\ripple20k.npz --out models\ripple_bc.zip --epochs 5
if errorlevel 1 goto failed
echo Pretraining complete. Next run 6_TRAIN.bat
pause
exit /b 0
:failed
echo PRETRAIN_FAILED - Keep the error above. Read START_HERE.md.
pause
exit /b 1
