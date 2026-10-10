@echo off
setlocal
cd /d "%~dp0"
echo IMPORTANT: STOP AutoLeague before starting. Takes substantial time for many model backups.
echo Scans ALL native-compatible .pt files. DOES NOT overwrite champion or checkpoints.
if not exist ".venv\Scripts\python.exe" (echo Missing local .venv. Extract into original Chat_GPT_AI folder. & pause & exit /b 1)
".venv\Scripts\python.exe" -u model_tournament.py
if errorlevel 1 (echo Stopped or failed. Restart to reuse completed evaluations. & pause & exit /b 1)
echo Check model_tournament_reports for leaderboard.csv and tournament.json.
pause
