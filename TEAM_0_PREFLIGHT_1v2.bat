@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe afk_team_research.py preflight --ours 1 --them 2 --scenario pressure
pause
