@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" export_rlbot_v4.py --name ChatGPT_AI_Cycle09
if errorlevel 1 pause
