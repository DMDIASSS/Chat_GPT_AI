@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" export_rlbot_v4.py --checkpoint "data\tactical_balance\candidate.pt" --name ChatGPT_AI_TacticalBalance
if errorlevel 1 pause
