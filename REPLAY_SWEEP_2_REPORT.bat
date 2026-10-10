@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe afk_replay_sweep.py summary
pause
