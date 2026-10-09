@echo off
setlocal
cd /d "%~dp0"
if not exist "data\datasets\nexto_rollouts" (
 echo No Nexto rollouts yet. Run COLLECT_NEXTO_ROLLOUTS.bat first.
 pause
 exit /b 1
)
if exist "data\bc_policy.pt" (
 ".venv\Scripts\python.exe" distill_nexto.py --dataset "data\datasets\nexto_rollouts" --out "data\nexto_student_policy.pt" --init "data\bc_policy.pt" --epochs 12 --batch 256
) else (
 ".venv\Scripts\python.exe" distill_nexto.py --dataset "data\datasets\nexto_rollouts" --out "data\nexto_student_policy.pt" --epochs 12 --batch 256
)
if errorlevel 1 echo ERROR: Distillation failed; inspect traceback.
pause
