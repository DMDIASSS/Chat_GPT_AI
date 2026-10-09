@echo off
cd /d "%~dp0"
title Chat GPT AI - Native Nexto fine-tuned selfplay
.venv\Scripts\python.exe watch_latest_ai.py --model native --actions sample --start kickoff
pause
