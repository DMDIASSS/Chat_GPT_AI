@echo off
cd /d "%~dp0"
echo Isolated Cycle 9 finishing PPO, 8192 total decision ticks (resumable).
echo STOP regular AutoLeague and AFK trainers first! Ctrl+C stops after last saved PPO rollout.
echo It NEVER promotes / replaces the main champion.
".venv\Scripts\python.exe" -u finishing_train.py --mode train --steps 8192 --rollout 256 --eval-games 40 --eval-decisions 450
if errorlevel 1 echo Training stopped / failed. Re-run this BAT to resume the candidate.
pause
