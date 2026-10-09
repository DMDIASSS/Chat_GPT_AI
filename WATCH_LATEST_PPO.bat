@echo off
cd /d "%~dp0"
title Chat GPT AI - Highest PPO checkpoint selfplay
.venv\Scripts\python.exe watch_latest_ai.py --model ppo --actions sample --start kickoff
pause
