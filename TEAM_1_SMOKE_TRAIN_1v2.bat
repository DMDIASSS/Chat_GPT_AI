@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe afk_team_research.py train --ours 1 --them 2 --scenario pressure --steps 512 --rollout 128 --seed 20261010
pause
