@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" afk_replay_tas_learning.py train
pause
