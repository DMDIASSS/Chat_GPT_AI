@echo off
cd /d "%~dp0"
"..\..\.venv\Scripts\python.exe" hub_cli.py create defense_1v2_trial_01 --preset "Defense Under Pressure 1v2"
pause
