@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: no virtualenv&pause&exit /b 1)
echo GUARDED REPLAY + TAS LEARNING. No champion will be replaced.
echo Real TAS files are audited only, not trained without verified state alignment.
".venv\Scripts\python.exe" afk_replay_tas_learning.py pipeline --replays "data\replays" --tas-folder "data\tas" --max-samples 60000 --games 200
if errorlevel 1 (echo Learning pipeline stopped with an error. Read output and reports.&pause&exit /b 1)
echo Done. Inspect data\afk_improved\learning\reports. No promotion performed.
pause
