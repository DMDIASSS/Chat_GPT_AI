@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" afk_replay_tas_learning.py verify --games 200 --decisions 750
pause
