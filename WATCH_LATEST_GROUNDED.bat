@echo off
cd /d "%~dp0"
title Chat GPT AI - Latest in grounded scenarios
.venv\Scripts\python.exe watch_latest_ai.py --model auto --actions sample --start grounded
pause
