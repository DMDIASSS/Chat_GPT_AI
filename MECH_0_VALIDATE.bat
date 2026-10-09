@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Extract into the Chat_GPT_AI root folder.&pause&exit /b 1)
".venv\Scripts\python.exe" -c "import native_nexto,nexto_teacher,mechanics_tasks,mechanics_scenarios,torch; from pathlib import Path; assert Path('data/native_nexto/best_10k.pt').is_file(), 'Back up best_10k.pt first'; print('Native model, Nexto teacher, mechanics modules and best_10k.pt are present')"
if errorlevel 1 (echo Setup FAILED&pause&exit /b 1)
".venv\Scripts\python.exe" -m py_compile mechanics_scenarios.py mechanics_tasks.py mechanics_train.py mechanics_evaluate.py
if errorlevel 1 (echo Compile FAILED&pause&exit /b 1)
echo Setup validated. No training started.
pause
