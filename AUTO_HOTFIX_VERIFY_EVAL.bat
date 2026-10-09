@echo off
setlocal
cd /d "%~dp0"
echo Checking the PREVIOUSLY CRASHED evaluator using existing saved champion and candidate.
echo READ ONLY. No training, saves, promotion, deletion or rollback.
if not exist .venv\Scripts\python.exe (echo ERROR: Missing virtual environment. & pause & exit /b 1)
.venv\Scripts\python.exe -u auto_league_eval_check.py --games 8 --decisions 180
if errorlevel 1 (echo HOTFIX CHECK FAILED. Copy the error and send it to ChatGPT. & pause & exit /b 1)
echo HOTFIX CHECK PASSED. You can resume with AUTO_1_START.bat
pause
