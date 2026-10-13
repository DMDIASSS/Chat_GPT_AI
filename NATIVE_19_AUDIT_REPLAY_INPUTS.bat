@echo off
cd /d "%~dp0"
echo Read-only audit of 12 raw replays and held-out imitation. Parsing is cached.
.venv\Scripts\python.exe -u slater_replay_input_audit.py
pause
