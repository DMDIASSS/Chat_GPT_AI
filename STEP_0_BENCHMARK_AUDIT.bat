@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Extract into original Chat_GPT_AI folder. & pause & exit /b 1)
echo SANITY CHECK: Nexto vs Nexto, same model both cars. Strong asymmetry could indicate evaluation bug.
".venv\Scripts\python.exe" benchmark_audit.py --mirror-nexto --games 20 --seed 123 --episode-decisions 750
if errorlevel 1 echo ERROR: Audit did not finish successfully.
echo If this audit shows a strong side advantage, investigate before training the student.
pause
