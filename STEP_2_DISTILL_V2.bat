@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Extract these files into Chat_GPT_AI. & pause & exit /b 1)
if not exist "data\nexto_student_policy.pt" (echo Missing current student weights. & pause & exit /b 1)
if exist "data\nexto_student_v2.pt" (
 echo An earlier v2 model already exists. It will NOT be overwritten.
 echo Move it to a backup location manually before trying again.
 pause
 exit /b 1
)
echo Training new student with Nexto hard-action guidance and soft probabilities.
".venv\Scripts\python.exe" distill_v2.py --init data\nexto_student_policy.pt --output data\nexto_student_v2.pt --epochs 30 --batch 256 --hard-weight 0.65 --patience 6
if errorlevel 1 (echo ERROR: distillation failed. & pause & exit /b 1)
echo NEXT: run STEP_3_BENCHMARK_V2.bat
pause
