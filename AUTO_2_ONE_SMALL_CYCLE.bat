@echo off
setlocal
cd /d "%~dp0"
echo One safeguarded smoke cycle only. Starts or resumes the SAME main league as AUTO_1_START.
echo Only 2,048 decisions; NOT a reliable proof of bot improvement.
.venv\Scripts\python.exe -u auto_league.py --source "data\native_nexto\best_10k.pt" --segment-decisions 2048 --eval-games 24 --max-cycles 1 --no-promote --backup-minutes 5 --device cpu
if errorlevel 1 echo Check error messages above.
pause
