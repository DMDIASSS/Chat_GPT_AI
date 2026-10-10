@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe afk_replay_sweep.py train --trials 1 --epochs 2
pause
