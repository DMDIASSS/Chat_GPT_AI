@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing project .venv & pause & exit /b 1)
".venv\Scripts\python.exe" afk_improved_runner.py --check
if errorlevel 1 pause
".venv\Scripts\python.exe" auto_league.py --source "data\autoleague\backups\20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt" --data-dir "data\afk_improved\league" --preflight --no-replays
pause
