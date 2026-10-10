@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" afk_replay_tas_learning.py build "data\replays" --max-samples 60000
pause
