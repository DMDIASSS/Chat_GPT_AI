@echo off
cd /d "%~dp0"
echo MECHANICS STAGE 1: recovery, 1024 decisions, saved separately from best_10k.pt
".venv\Scripts\python.exe" -u mechanics_train.py --stage recovery --steps 1024 --rollout 256 --minibatch 64 --epochs 2 --episode-decisions 100 --device cpu
if errorlevel 1 (echo FAILED. Save the traceback.&pause&exit /b 1)
echo Completed. Run MECH_2_EVALUATE_RECOVERY.bat next.
pause
