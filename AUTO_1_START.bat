@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo ERROR: Missing .venv & pause & exit /b 1)
echo Chat GPT AI AUTOLEAGUE ^| runs until Ctrl+C.
echo Start model: 10K Native Nexto ^| backs up every 5 minutes of wall-clock training.
echo Training/evaluation files ONLY under data\autoleague. Existing Nexto models untouched.
echo Replay downloads require BALLCHASING_TOKEN; if absent, skip without stopping training.
.venv\Scripts\python.exe -u auto_league.py --source "data\native_nexto\best_10k.pt" --backup-minutes 5 --segment-decisions 8192 --eval-games 40 --device cpu
if errorlevel 1 echo Run stopped or failed. Check above. Champion and previous backups remain safe.
pause
