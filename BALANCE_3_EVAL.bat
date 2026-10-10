@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" balance_train.py --mode eval --games 120 --decisions 750
if errorlevel 1 pause
