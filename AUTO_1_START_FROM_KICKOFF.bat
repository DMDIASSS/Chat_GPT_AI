@echo off
setlocal
cd /d "%~dp0"
echo Separate league starting from your kickoff-trained checkpoint (7-0 in the small test).
echo Writes ONLY under data\autoleague_kickoff. Does not overwrite 10K or normal league.
if not exist data\mechanics\kickoff\last.pt (echo ERROR: Missing kickoff checkpoint. & pause & exit /b 1)
.venv\Scripts\python.exe -u auto_league.py --source "data\mechanics\kickoff\last.pt" --data-dir "data\autoleague_kickoff" --backup-minutes 5 --segment-decisions 8192 --eval-games 40 --device cpu
if errorlevel 1 echo Failed or stopped. Backup checkpoints remain safe.
pause
