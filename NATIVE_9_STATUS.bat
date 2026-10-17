@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe slater_native_campaign.py status --run native_quality02
pause
