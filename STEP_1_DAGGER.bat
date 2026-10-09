@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Extract these files directly into the original Chat_GPT_AI folder. & pause & exit /b 1)
if not exist "data\nexto_student_policy.pt" (echo Missing trained Nexto student file. & pause & exit /b 1)
echo Collecting 15000 STUDENT-influenced Nexto-labeled decisions. You can interrupt; saved shards survive.
".venv\Scripts\python.exe" collect_dagger.py --checkpoint data\nexto_student_policy.pt --decisions 15000 --teacher-probability 0.5 --scenarios grounded --teacher-device cpu
if errorlevel 1 (echo ERROR during collection. & pause & exit /b 1)
".venv\Scripts\python.exe" inspect_nexto_dataset.py
if errorlevel 1 (echo ERROR: dataset validation failed. & pause & exit /b 1)
echo NEXT: run STEP_2_DISTILL_V2.bat
pause
