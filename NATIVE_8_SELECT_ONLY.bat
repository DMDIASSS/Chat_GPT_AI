@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u slater_native_campaign.py select --run native_quality_screen01
pause
