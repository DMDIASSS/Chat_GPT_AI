@echo off
cd /d "%~dp0"
echo Reuses existing replay-control coverage and bank; no raw re-parsing.
.venv\Scripts\python.exe -u slater_replay_input_audit.py --raw-count 0
pause
