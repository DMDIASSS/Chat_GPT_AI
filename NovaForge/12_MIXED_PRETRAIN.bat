@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py pretrain --dataset datasets\mixed40k.npz --out models\mixed_bc.zip --epochs 5
if errorlevel 1 goto failed
echo Pretraining complete. Next run 13_MIXED_TRAIN.bat
pause
exit /b 0
:failed
echo PRETRAIN_FAILED - Keep the error above.
pause
exit /b 1
