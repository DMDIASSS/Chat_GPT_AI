@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Install files in existing Chat GPT AI folder.
 pause
 exit /b 1
)
if not exist "data\datasets\nexto_teacher_1v1.npz" (
 echo ERROR: Run BUILD_NEXTO_DATA.bat first.
 pause
 exit /b 1
)
if exist "data\bc_policy.pt" (
 echo Using your human-replay-trained model as the initial student.
 ".venv\Scripts\python.exe" distill_nexto.py --init "data\bc_policy.pt" --epochs 12 --batch 256
) else (
 echo Human replay model missing; distilling into a fresh student network.
 ".venv\Scripts\python.exe" distill_nexto.py --epochs 12 --batch 256
)
if errorlevel 1 (
 echo ERROR: Distillation failed.
) else (
 echo Done. If a better student was saved, next is START_STUDENT_PPO.bat.
)
pause
