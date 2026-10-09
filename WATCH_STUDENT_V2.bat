@echo off
cd /d "%~dp0"
title Chat GPT AI - Distilled Student selfplay
.venv\Scripts\python.exe watch_latest_ai.py --model student --actions sample --start kickoff
pause
